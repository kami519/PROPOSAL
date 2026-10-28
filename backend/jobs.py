from __future__ import annotations

import logging
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import (
    DOWNLOAD_CONCURRENCY,
    DOWNLOAD_WORKERS,
    JOBS_DIR,
    JOB_TTL_SECONDS,
    MAX_FILESIZE_BYTES,
    MAX_JOBS,
    MIN_FREE_BYTES,
)
from .downloader import download_url
from .errors import AppError, DownloadCancelled, DownloadPaused

logger = logging.getLogger("clipdock.jobs")


@dataclass
class Job:
    id: str
    url: str
    tier: str
    directory: Path
    title: str = "未命名视频"
    thumbnail: str | None = None
    platform: str | None = None
    status: str = "queued"
    progress: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int | None = None
    speed: str | None = None
    eta: str | None = None
    filename: str | None = None
    filepath: Path | None = None
    filesize: int | None = None
    error: str | None = None
    error_code: str | None = None
    pause_requested: bool = False
    cancel_requested: bool = False
    future: Any = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "progress": round(self.progress, 1),
            "downloadedBytes": self.downloaded_bytes,
            "totalBytes": self.total_bytes,
            "speed": self.speed,
            "eta": self.eta,
            "title": self.title,
            "thumbnail": self.thumbnail,
            "platform": self.platform,
            "format": self.tier,
            "filename": self.filename,
            "filesize": self.filesize,
            "downloadUrl": f"/api/jobs/{self.id}/file" if self.status == "done" else None,
            "error": self.error,
            "errorCode": self.error_code,
            "canPause": self.status in {"queued", "downloading"},
            "canResume": self.status == "paused",
            "canCancel": self.status in {
                "queued",
                "downloading",
                "pausing",
                "paused",
                "processing",
            },
            "createdAt": int(self.created_at),
            "updatedAt": int(self.updated_at),
        }


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=DOWNLOAD_WORKERS, thread_name_prefix="clipdock-dl"
        )
        self._cleanup_stop = threading.Event()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            name="clipdock-cleanup",
            daemon=True,
        )
        self._cleanup_thread.start()

    def _check_capacity(self) -> None:
        try:
            free = shutil.disk_usage(JOBS_DIR).free
        except OSError:
            free = MIN_FREE_BYTES
        if free < MIN_FREE_BYTES + MAX_FILESIZE_BYTES:
            raise AppError("DISK_FULL", "服务器临时空间不足，请稍后再试。", 507)

        with self._lock:
            active = sum(
                1
                for job in self._jobs.values()
                if job.status
                in {"queued", "downloading", "pausing", "paused", "processing", "cancelling"}
            )
        if active >= MAX_JOBS:
            raise AppError("TOO_BUSY", "当前排队任务太多，请稍后再试。", 429)
        if DOWNLOAD_CONCURRENCY:
            running = sum(
                1
                for job in self._jobs.values()
                if job.status in {"downloading", "processing"}
            )
            if running >= DOWNLOAD_CONCURRENCY:
                raise AppError(
                    "TOO_BUSY",
                    "当前已有视频在下载，请等它完成后或暂停后再试。",
                    429,
                )

    def create(
        self,
        *,
        url: str,
        tier: str,
        title: str | None = None,
        thumbnail: str | None = None,
        platform: str | None = None,
    ) -> dict[str, Any]:
        self._check_capacity()
        job_id = uuid.uuid4().hex
        directory = JOBS_DIR / job_id
        directory.mkdir(parents=True, exist_ok=True)
        job = Job(
            id=job_id,
            url=url,
            tier=tier,
            directory=directory,
            title=(title or "未命名视频")[:240],
            thumbnail=thumbnail[:2048] if thumbnail else None,
            platform=(platform or "视频平台")[:80],
        )
        with self._lock:
            self._jobs[job_id] = job
            job.future = self._executor.submit(self._run, job)
        return job.public()

    def _update(self, job: Job, **values: Any) -> None:
        aliases = {
            "downloadedBytes": "downloaded_bytes",
            "totalBytes": "total_bytes",
        }
        with self._lock:
            for key, value in values.items():
                setattr(job, aliases.get(key, key), value)
            job.updated_at = time.time()

    def _checkpoint(self, job: Job) -> None:
        if job.cancel_requested:
            raise DownloadCancelled()
        if job.pause_requested:
            raise DownloadPaused()

    def _mark_cancelled(self, job: Job) -> None:
        shutil.rmtree(job.directory, ignore_errors=True)
        self._update(
            job,
            status="cancelled",
            speed=None,
            eta=None,
            filepath=None,
            filename=None,
            filesize=None,
            progress=0.0,
            downloaded_bytes=0,
            total_bytes=None,
            error=None,
            error_code=None,
        )

    def _run(self, job: Job) -> None:
        self._update(job, status="downloading", progress=0.0)
        try:
            path, filename = download_url(
                job.url,
                job.tier,
                job.directory,
                progress=lambda **values: self._update(job, **values),
                checkpoint=lambda: self._checkpoint(job),
            )
            if job.cancel_requested:
                self._mark_cancelled(job)
                return
            final_size = path.stat().st_size
            self._update(
                job,
                status="done",
                progress=100.0,
                speed=None,
                eta=None,
                filepath=path,
                filename=filename,
                filesize=final_size,
                downloaded_bytes=final_size,
                total_bytes=final_size,
                error=None,
                error_code=None,
                pause_requested=False,
            )
        except DownloadPaused:
            self._update(
                job,
                status="paused",
                speed=None,
                eta=None,
                error=None,
                error_code=None,
            )
        except DownloadCancelled:
            self._mark_cancelled(job)
        except AppError as exc:
            if job.cancel_requested:
                self._mark_cancelled(job)
                return
            logger.warning("Job %s failed: %s (%s)", job.id, exc.message, exc.code)
            self._update(
                job,
                status="error",
                speed=None,
                eta=None,
                error=exc.message,
                error_code=exc.code,
            )
        except Exception as exc:  # noqa: BLE001
            if job.cancel_requested:
                self._mark_cancelled(job)
                return
            logger.exception("Job %s crashed", job.id)
            self._update(
                job,
                status="error",
                speed=None,
                eta=None,
                error="下载失败，请稍后重试。",
                error_code="INTERNAL_ERROR",
            )

    def pause(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise AppError("JOB_NOT_FOUND", "任务不存在或已过期。", 404)
            if job.status == "paused":
                return job.public()
            if job.status == "processing":
                raise AppError(
                    "CANNOT_PAUSE",
                    "音视频正在合并，暂时不能暂停；可以取消，取消会在合并结束后生效。",
                    409,
                )
            if job.status not in {"queued", "downloading", "pausing"}:
                raise AppError("JOB_NOT_ACTIVE", "这个任务当前不能暂停。", 409)

            job.pause_requested = True
            job.updated_at = time.time()
            if job.status == "queued" and job.future is not None and job.future.cancel():
                job.status = "paused"
            else:
                job.status = "pausing"
            return job.public()

    def resume(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise AppError("JOB_NOT_FOUND", "任务不存在或已过期。", 404)
            if job.status != "paused":
                raise AppError("JOB_NOT_PAUSED", "只有已暂停的任务才能继续。", 409)
            job.pause_requested = False
            job.cancel_requested = False
            job.status = "queued"
            job.updated_at = time.time()
            job.future = self._executor.submit(self._run, job)
            return job.public()

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise AppError("JOB_NOT_FOUND", "任务不存在或已过期。", 404)
            if job.status in {"done", "error", "cancelled"}:
                raise AppError("JOB_NOT_ACTIVE", "这个任务已经结束。", 409)
            if job.status == "paused":
                self._mark_cancelled(job)
                return job.public()
            if job.status == "queued" and job.future is not None and job.future.cancel():
                self._mark_cancelled(job)
                return job.public()

            job.cancel_requested = True
            job.pause_requested = False
            job.status = "cancelling"
            job.updated_at = time.time()
            return job.public()

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise AppError("JOB_NOT_FOUND", "任务不存在或已过期。", 404)
            return job.public()

    def get_file(self, job_id: str) -> tuple[Path, str, str]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise AppError("JOB_NOT_FOUND", "任务不存在或已过期。", 404)
            if job.status != "done" or not job.filepath:
                raise AppError("JOB_NOT_READY", "文件还没有准备好。", 409)
            path = job.filepath
            filename = job.filename or path.name
        if not path.exists():
            raise AppError("FILE_EXPIRED", "文件已过期并被清理，请重新下载。", 410)
        suffix = path.suffix.lower()
        media_type = {
            ".mp4": "video/mp4",
            ".mkv": "video/x-matroska",
            ".webm": "video/webm",
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
        }.get(suffix, "application/octet-stream")
        return path, filename, media_type

    def _cleanup_once(self) -> None:
        cutoff = time.time() - JOB_TTL_SECONDS
        expired: list[Job] = []
        with self._lock:
            for job_id, job in list(self._jobs.items()):
                if job.status in {"done", "error", "paused", "cancelled"} and job.updated_at < cutoff:
                    expired.append(job)
                    self._jobs.pop(job_id, None)
        for job in expired:
            shutil.rmtree(job.directory, ignore_errors=True)

        # Remove orphan directories left by a crash or a deleted job.
        try:
            with self._lock:
                known = {job.directory.name for job in self._jobs.values()}
            for child in JOBS_DIR.iterdir():
                if not child.is_dir() or child.name in known:
                    continue
                try:
                    if child.stat().st_mtime < cutoff:
                        shutil.rmtree(child, ignore_errors=True)
                except OSError:
                    continue
        except OSError:
            pass

    def _cleanup_loop(self) -> None:
        while not self._cleanup_stop.wait(60):
            try:
                self._cleanup_once()
            except Exception:  # noqa: BLE001
                logger.exception("Cleanup pass failed")

    def count(self) -> int:
        with self._lock:
            return len(self._jobs)

    def shutdown(self) -> None:
        self._cleanup_stop.set()
        self._executor.shutdown(wait=False, cancel_futures=True)


job_store = JobStore()
