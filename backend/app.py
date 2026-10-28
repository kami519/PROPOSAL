from __future__ import annotations

import asyncio
import logging
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import yt_dlp.version
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from .config import (
    ALLOWED_FORMATS,
    APP_NAME,
    APP_VERSION,
    COOKIES_FILE,
    FRONTEND_DIST,
    JOBS_DIR,
    SUMMARY_ARTICLE_ENABLED,
    SUMMARY_ENABLED,
    SUMMARY_LLM_CONCURRENCY,
    SUMMARY_MODEL,
    SUMMARY_TRANSCRIBE_WORKERS,
    SUMMARY_WORKERS,
)
from .downloader import FFMPEG_PATH, analyze_url, clean_text
from .errors import AppError
from .jobs import job_store
from .library import library_store
from .summary import summary_store, whisper_available
from .security import normalize_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("clipdock.app")

_analysis_semaphore = asyncio.Semaphore(4)
_analysis_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_ANALYSIS_CACHE_TTL = 10 * 60


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("%s %s ready; downloads=%s", APP_NAME, APP_VERSION, JOBS_DIR)
    try:
        removed = library_store.purge_trash()
        if removed:
            logger.info("已清理 %s 篇过期回收站笔记", removed)
    except Exception:  # noqa: BLE001
        logger.exception("回收站清理失败")
    yield
    job_store.shutdown()
    summary_store.shutdown()


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)


class AnalyzeRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4096)


class JobMeta(BaseModel):
    title: str | None = Field(default=None, max_length=512)
    thumbnail: str | None = Field(default=None, max_length=4096)
    platform: str | None = Field(default=None, max_length=120)


class JobRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4096)
    format: Literal["720p", "1080p", "best", "audio"] = "720p"
    meta: JobMeta | None = None


class SummaryRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4096)
    title: str | None = Field(default=None, max_length=512)
    thumbnail: str | None = Field(default=None, max_length=4096)
    platform: str | None = Field(default=None, max_length=120)
    uploader: str | None = Field(default=None, max_length=240)
    duration: int = Field(default=0, ge=0, le=24 * 60 * 60)


class BatchIds(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=200)


def _public_error(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_public_error(exc.code, exc.message),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=_public_error("INVALID_REQUEST", "请求参数不正确。"),
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error for %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content=_public_error("INTERNAL_ERROR", "服务器开小差了，请稍后再试。"),
    )


def _safe_thumbnail(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return value[:2048]


def _remember_analysis(url: str, data: dict[str, Any]) -> None:
    now = time.time()
    _analysis_cache[url] = (now, data)
    if len(_analysis_cache) > 100:
        for key, (created_at, _) in list(_analysis_cache.items()):
            if now - created_at > _ANALYSIS_CACHE_TTL or len(_analysis_cache) > 80:
                _analysis_cache.pop(key, None)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    try:
        free = shutil.disk_usage(JOBS_DIR).free
    except OSError:
        free = 0
    return {
        "ok": True,
        "name": APP_NAME,
        "version": APP_VERSION,
        "ytDlpVersion": yt_dlp.version.__version__,
        "ffmpeg": str(FFMPEG_PATH),
        "freeBytes": free,
        "jobs": job_store.count(),
        "cookiesConfigured": bool(COOKIES_FILE and COOKIES_FILE.exists()),
        "summaryConfigured": SUMMARY_ENABLED,
        "summaryModel": SUMMARY_MODEL,
        "articleEnabled": SUMMARY_ARTICLE_ENABLED,
        "whisperAvailable": whisper_available(),
        "summaryActive": summary_store.count_active(),
        "summaryWorkers": SUMMARY_WORKERS,
        "transcribeWorkers": SUMMARY_TRANSCRIBE_WORKERS,
        "llmConcurrency": SUMMARY_LLM_CONCURRENCY,
    }


@app.post("/api/analyze")
async def analyze(request: AnalyzeRequest) -> dict[str, Any]:
    url = normalize_url(request.url)
    cached = _analysis_cache.get(url)
    if cached and time.time() - cached[0] < _ANALYSIS_CACHE_TTL:
        return cached[1]

    async with _analysis_semaphore:
        data = await run_in_threadpool(analyze_url, url)
    _remember_analysis(url, data)
    return data


@app.post("/api/jobs")
async def create_job(request: JobRequest, http_request: Request) -> dict[str, Any]:
    url = normalize_url(request.url)
    tier = request.format
    if tier not in ALLOWED_FORMATS:
        raise AppError("INVALID_FORMAT", "不支持的清晰度选项。", 422)

    meta = request.meta
    if meta is None:
        cached = _analysis_cache.get(url)
        if cached and time.time() - cached[0] < _ANALYSIS_CACHE_TTL:
            cached_data = cached[1]
            meta = JobMeta(
                title=cached_data.get("title"),
                thumbnail=cached_data.get("thumbnail"),
                platform=cached_data.get("platform"),
            )

    job = job_store.create(
        url=url,
        tier=tier,
        title=clean_text(meta.title, 240) if meta and meta.title else None,
        thumbnail=_safe_thumbnail(meta.thumbnail) if meta else None,
        platform=clean_text(meta.platform, 80) if meta and meta.platform else None,
    )
    return job


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    return job_store.get(job_id)


@app.post("/api/jobs/{job_id}/pause")
async def pause_job(job_id: str) -> dict[str, Any]:
    return job_store.pause(job_id)


@app.post("/api/jobs/{job_id}/resume")
async def resume_job(job_id: str) -> dict[str, Any]:
    return job_store.resume(job_id)


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict[str, Any]:
    return job_store.cancel(job_id)


@app.get("/api/jobs/{job_id}/file")
async def get_job_file(job_id: str):
    path, filename, media_type = job_store.get_file(job_id)
    return FileResponse(
        path=path,
        media_type=media_type,
        filename=filename,
        headers={"Cache-Control": "private, no-store"},
    )


@app.get("/api/summaries")
async def list_summaries(
    ids: str = "",
    status: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    id_list = [part.strip() for part in ids.split(",") if part.strip()]
    return summary_store.list_jobs(ids=id_list, status=status, limit=limit)


@app.post("/api/summaries")
async def create_summary(request: SummaryRequest) -> dict[str, Any]:
    url = normalize_url(request.url)
    return summary_store.create(
        url=url,
        title=clean_text(request.title, 240) if request.title else None,
        thumbnail=_safe_thumbnail(request.thumbnail),
        platform=clean_text(request.platform, 80) if request.platform else None,
        uploader=clean_text(request.uploader, 120) if request.uploader else None,
        duration=request.duration,
    )


@app.get("/api/summaries/{summary_id}")
async def get_summary(summary_id: str) -> dict[str, Any]:
    return summary_store.get(summary_id)


@app.post("/api/summaries/{summary_id}/cancel")
async def cancel_summary(summary_id: str) -> dict[str, Any]:
    return summary_store.cancel(summary_id)


@app.post("/api/summaries/{summary_id}/retry")
async def retry_summary(summary_id: str) -> dict[str, Any]:
    return summary_store.retry(summary_id)


@app.get("/api/summaries/{summary_id}/transcript")
async def get_summary_transcript(summary_id: str) -> dict[str, Any]:
    return summary_store.transcript(summary_id)


@app.get("/api/summaries/{summary_id}/article")
async def get_summary_article(summary_id: str) -> dict[str, Any]:
    return summary_store.article(summary_id)


@app.post("/api/summaries/{summary_id}/article")
async def create_summary_article(summary_id: str) -> dict[str, Any]:
    return summary_store.request_article(summary_id)


@app.get("/api/library")
async def list_library(
    q: str = "",
    status: str = "",
    platform: str = "",
    sort: str = "updated",
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    return library_store.list_notes(
        query=q,
        status=status,
        platform=platform,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@app.get("/api/library/{note_id}")
async def get_library_note(note_id: str) -> dict[str, Any]:
    note = library_store.get(note_id)
    if note is None:
        raise AppError("NOTE_NOT_FOUND", "笔记不存在。", 404)
    return note


@app.get("/api/library/{note_id}/content")
async def get_library_content(note_id: str) -> PlainTextResponse:
    note = library_store.get(note_id)
    if note is None:
        raise AppError("NOTE_NOT_FOUND", "笔记不存在。", 404)
    try:
        content = library_store.read_content(note_id)
    except FileNotFoundError as exc:
        raise AppError("NOTE_FILE_MISSING", "笔记文件不存在。", 404) from exc
    return PlainTextResponse(
        content,
        media_type="text/markdown; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/library/{note_id}/download")
async def download_library_note(note_id: str):
    note = library_store.get(note_id)
    path = library_store.content_path(note_id)
    if note is None or path is None:
        raise AppError("NOTE_NOT_FOUND", "笔记文件不存在。", 404)
    filename = note.get("fileName") or f"{note_id}.md"
    return FileResponse(
        path=path,
        media_type="text/markdown; charset=utf-8",
        filename=filename,
        headers={"Cache-Control": "private, no-store"},
    )


@app.post("/api/library/batch-download")
async def batch_download_library(request: BatchIds):
    try:
        path = library_store.build_zip(request.ids)
    except ValueError as exc:
        raise AppError("NOTE_SELECTION_EMPTY", str(exc), 400) from exc
    return FileResponse(
        path=path,
        media_type="application/zip",
        filename=path.name,
        background=BackgroundTask(path.unlink, missing_ok=True),
        headers={"Cache-Control": "private, no-store"},
    )


@app.post("/api/library/batch-delete")
async def batch_delete_library(request: BatchIds) -> dict[str, Any]:
    if not request.ids:
        raise AppError("NOTE_SELECTION_EMPTY", "请先选择要删除的笔记。", 400)
    return library_store.mark_trashed(request.ids)


@app.post("/api/library/batch-restore")
async def batch_restore_library(request: BatchIds) -> dict[str, Any]:
    if not request.ids:
        raise AppError("NOTE_SELECTION_EMPTY", "请先选择要恢复的笔记。", 400)
    return library_store.restore(request.ids)


# --- Static frontend -------------------------------------------------------
# API routes are declared before this catch-all. Mounted assets are handled by
# StaticFiles; unknown non-API paths fall back to the SPA entry point.
if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise AppError("NOT_FOUND", "接口不存在。", 404)
        dist_root = FRONTEND_DIST.resolve()
        target = (FRONTEND_DIST / full_path).resolve()
        if target.is_file() and (target == dist_root or dist_root in target.parents):
            return FileResponse(target)
        index = FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(index)
        raise AppError("FRONTEND_NOT_BUILT", "前端还没有构建，请先运行 npm run build。", 503)

else:

    @app.get("/", include_in_schema=False)
    async def root_info() -> HTMLResponse:
        return HTMLResponse(
            "<h1>ClipDock API is running</h1>"
            "<p>Frontend is not built yet. Run <code>cd frontend &amp;&amp; npm run build</code>.</p>"
        )
