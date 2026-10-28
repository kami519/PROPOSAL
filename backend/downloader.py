from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Callable

import imageio_ffmpeg
import yt_dlp
from yt_dlp.utils import DownloadError

from .config import (
    COOKIES_FILE,
    MAX_DURATION_SECONDS,
    MAX_FILESIZE_BYTES,
    PLATFORM_NAMES,
    PROXY,
)
from .errors import AppError, DownloadCancelled, DownloadPaused
from .formats import build_formats, human_duration, human_size, label_for_height, selector_for

logger = logging.getLogger("clipdock.downloader")
logging.getLogger("yt_dlp").setLevel(logging.ERROR)

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_MISSING_FORMATS_RE = re.compile(
    r"Format\(s\)\s+(.+?)\s+are missing;.*?(?:premium member|login|cookies)",
    re.IGNORECASE,
)
_HIGH_QUALITY_HINT_RE = re.compile(r"(4K|8K|2K|HDR|杜比|Dolby)", re.IGNORECASE)


class YdlLogger:
    def __init__(self) -> None:
        self.debug_messages: list[str] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def debug(self, msg: str) -> None:
        # yt-dlp sends to_screen() information here. Bilibili, for example,
        # reports which qualities were withheld behind login/membership in a
        # debug message, not a warning.
        if len(self.debug_messages) < 500:
            self.debug_messages.append(str(msg))

    def warning(self, msg: str) -> None:
        self.warnings.append(str(msg))

    def error(self, msg: str) -> None:
        self.errors.append(str(msg))

    def all_messages(self) -> str:
        return "\n".join(self.errors + self.warnings)


def clean_text(value: Any, limit: int = 240) -> str:
    text = _CONTROL_RE.sub(" ", str(value or "")).strip()
    return text[:limit]


def _platform_name(info: dict[str, Any]) -> str:
    key = str(info.get("extractor_key") or info.get("extractor") or "").strip()
    lowered = key.lower()
    if lowered in PLATFORM_NAMES:
        return PLATFORM_NAMES[lowered]
    # yt-dlp keys are often CamelCase ("BiliBili", "TikTok", "Twitter").
    for candidate, name in PLATFORM_NAMES.items():
        if candidate.replace(":", "") in lowered.replace(":", ""):
            return name
    return key or "视频平台"


def _quality_notice(
    adapter: YdlLogger,
    max_height: int | None,
    *,
    cookies_configured: bool,
) -> dict[str, Any] | None:
    """Turn yt-dlp's withheld-format messages into product-facing copy."""

    for message in adapter.debug_messages:
        match = _MISSING_FORMATS_RE.search(message)
        if not match:
            continue
        missing = [
            clean_text(part, 60)
            for part in match.group(1).split(",")
            if clean_text(part, 60)
        ]
        if not missing:
            continue
        # Don't nag users about a missing high-bitrate 1080P variant when the
        # point of this notice is a whole higher resolution tier (4K/HDR/etc.).
        if not any(_HIGH_QUALITY_HINT_RE.search(item) for item in missing):
            continue

        max_label = label_for_height(max_height)
        missing_text = "、".join(missing)
        if cookies_configured:
            text = (
                f"源站还有 {missing_text} 清晰度，但当前登录信息没有对应权限；"
                f"当前可下载最高 {max_label}。"
            )
        else:
            text = (
                f"源站还有 {missing_text} 清晰度，但需要登录或会员权限；"
                f"当前可下载最高 {max_label}。"
            )
        return {
            "code": "HIGHER_QUALITY_REQUIRES_LOGIN",
            "message": text,
            "missingFormats": missing,
            "maxAvailableHeight": max_height,
        }
    return None


def _best_thumbnail(info: dict[str, Any]) -> str | None:
    thumbnails = info.get("thumbnails") or []
    candidates = [item for item in thumbnails if item.get("url")]
    url = None
    if candidates:
        with_area = [item for item in candidates if item.get("width") or item.get("height")]
        if with_area:
            url = max(
                with_area,
                key=lambda item: (item.get("width") or 0) * (item.get("height") or 0),
            ).get("url")
        else:
            url = candidates[-1].get("url")
    url = url or info.get("thumbnail")
    if not url:
        return None
    url = str(url)
    if url.startswith("http://"):
        url = "https://" + url[len("http://") :]
    return url


def _base_opts(
    logger_adapter: YdlLogger,
    *,
    outtmpl: str | None = None,
    progress_hook: Callable[[dict[str, Any]], None] | None = None,
    postprocessor_hook: Callable[[dict[str, Any]], None] | None = None,
    audio_only: bool = False,
) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "playlist_items": "1",
        "socket_timeout": 25,
        "retries": 3,
        "fragment_retries": 3,
        "concurrent_fragment_downloads": 4,
        "windowsfilenames": True,
        "trim_file_name": 180,
        "merge_output_format": "mp4",
        "ffmpeg_location": FFMPEG_PATH,
        "max_filesize": MAX_FILESIZE_BYTES,
        "logger": logger_adapter,
        "noprogress": True,
    }
    if outtmpl:
        opts["outtmpl"] = outtmpl
    if progress_hook:
        opts["progress_hooks"] = [progress_hook]
    if postprocessor_hook:
        opts["postprocessor_hooks"] = [postprocessor_hook]
    if audio_only:
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    if COOKIES_FILE and COOKIES_FILE.exists():
        opts["cookiefile"] = str(COOKIES_FILE)
    if PROXY:
        opts["proxy"] = PROXY
    return opts


def _friendly_error(exc: BaseException, adapter: YdlLogger) -> AppError:
    raw = f"{exc}\n{adapter.all_messages()}"
    lower = raw.lower()

    if "sign in to confirm" in lower or "cookies" in lower or "login required" in lower:
        return AppError(
            "AUTH_REQUIRED",
            "这个平台需要登录信息。请配置 YTDLP_COOKIES，或换一个公开视频链接。",
            422,
        )
    if "drm" in lower or "protected" in lower and "content" in lower:
        return AppError(
            "DRM_PROTECTED",
            "这个视频有 DRM 版权保护，无法下载。请选择公开、非付费内容。",
            422,
        )
    if "unsupported url" in lower or "no suitable extractor" in lower:
        return AppError("UNSUPPORTED", "这个链接暂不支持，换一个公开视频链接试试。", 422)
    if "private video" in lower or "private" in lower and "video" in lower:
        return AppError("PRIVATE_VIDEO", "这是私密视频，无法访问。", 422)
    if "not available in your country" in lower or "geo" in lower and "block" in lower:
        return AppError("GEO_BLOCKED", "这个视频在当前地区不可播放，换一个链接试试。", 422)
    if "video unavailable" in lower or "removed" in lower or "does not exist" in lower:
        return AppError("UNAVAILABLE", "视频不存在、已删除或暂不可用。", 422)
    if "ffmpeg" in lower:
        return AppError(
            "FFMPEG_ERROR",
            "音视频合并失败，请检查 ffmpeg 是否可用后重试。",
            500,
        )
    if "timed out" in lower or "timeout" in lower:
        return AppError("TIMEOUT", "解析超时，请稍后重试或换一个链接。", 504)
    if "http error 403" in lower or "forbidden" in lower:
        return AppError("FORBIDDEN", "平台拒绝了请求，可能需要登录或稍后再试。", 422)
    if "max-filesize" in lower or "larger than max" in lower:
        return AppError("TOO_LARGE", "视频超过当前大小限制，暂时无法下载。", 413)

    logger.warning("Unmapped yt-dlp error: %s", raw[:2000])
    return AppError("DOWNLOAD_FAILED", "解析失败，请稍后重试或换一个链接。", 502)


def _validate_info(info: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(info, dict):
        raise AppError("ANALYZE_FAILED", "没有解析到视频信息。", 422)

    if info.get("_type") == "playlist":
        entries = [entry for entry in (info.get("entries") or []) if isinstance(entry, dict)]
        if not entries:
            raise AppError("EMPTY_PLAYLIST", "这个播放列表里没有可下载的视频。", 422)
        info = entries[0]

    if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming"}:
        raise AppError("LIVE_UNSUPPORTED", "直播和预告暂不支持，请等视频回放上线后再试。", 422)
    if info.get("_has_drm"):
        raise AppError("DRM_PROTECTED", "这个视频有 DRM 版权保护，无法下载。", 422)
    if info.get("availability") in {"private", "premium_only", "subscriber_only"}:
        raise AppError("PRIVATE_VIDEO", "这是私密或付费视频，无法访问。", 422)

    duration = info.get("duration") or 0
    try:
        duration = int(duration)
    except (TypeError, ValueError):
        duration = 0
    if duration and duration > MAX_DURATION_SECONDS:
        max_hours = MAX_DURATION_SECONDS / 3600
        raise AppError(
            "TOO_LONG",
            f"演示版只支持 {max_hours:g} 小时以内的视频，这个视频太长了。",
            422,
        )
    return info


def analyze_url(url: str) -> dict[str, Any]:
    adapter = YdlLogger()
    try:
        with yt_dlp.YoutubeDL(_base_opts(adapter)) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        raise _friendly_error(exc, adapter) from exc
    except Exception as exc:  # noqa: BLE001 - map to a user-facing error
        logger.exception("Unexpected analyze failure")
        raise _friendly_error(exc, adapter) from exc

    info = _validate_info(info)
    formats, max_height = build_formats(info)
    if not formats:
        raise AppError("NO_FORMATS", "没有找到可下载的清晰度，换一个链接试试。", 422)

    duration = int(info.get("duration") or 0)
    title = clean_text(info.get("title") or info.get("fulltitle") or "未命名视频")
    uploader = clean_text(info.get("uploader") or info.get("channel") or "未知作者", 120)
    platform = _platform_name(info)
    webpage_url = clean_text(info.get("webpage_url") or url, 2048)
    thumbnail = _best_thumbnail(info)
    quality_notice = _quality_notice(
        adapter,
        max_height,
        cookies_configured=bool(COOKIES_FILE and COOKIES_FILE.exists()),
    )

    return {
        "title": title,
        "uploader": uploader,
        "duration": duration,
        "durationText": human_duration(duration),
        "thumbnail": thumbnail,
        "webpageUrl": webpage_url,
        "platform": platform,
        "sourceHeight": max_height,
        "formats": formats,
        "qualityNotice": quality_notice,
    }


def _find_output(directory: Path) -> Path | None:
    files = [
        path
        for path in directory.rglob("*")
        if path.is_file()
        and path.suffix.lower() not in {".part", ".ytdl", ".temp", ".json", ".description"}
    ]
    if not files:
        return None
    files.sort(key=lambda path: path.stat().st_size, reverse=True)
    return files[0]


def download_url(
    url: str,
    tier: str,
    directory: Path,
    *,
    progress: Callable[..., None],
    checkpoint: Callable[[], None] | None = None,
) -> tuple[Path, str]:
    """Download one URL into directory and return (path, display filename).

    ``checkpoint`` is called from yt-dlp's progress hook. It lets the job store
    cooperatively pause or cancel a running download while keeping completed
    ``.part`` files for a later resume.
    """

    directory.mkdir(parents=True, exist_ok=True)
    adapter = YdlLogger()
    audio_only = tier == "audio"
    outtmpl = str(directory / "%(title).80B [%(id)s].%(ext)s")

    # yt-dlp reports progress per file. A 1080p download is usually a video
    # stream followed by an audio stream, so a naive percentage would jump from
    # 98% back to 0%. Keep the UI monotonically increasing instead.
    last_percent = 0.0

    def on_progress(data: dict[str, Any]) -> None:
        nonlocal last_percent
        if checkpoint:
            checkpoint()
        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded = data.get("downloaded_bytes") or 0
            percent = 0.0
            if total:
                percent = max(0.0, min(98.0, downloaded / total * 100))
            last_percent = max(last_percent, percent)
            speed = data.get("speed")
            progress(
                status="downloading",
                progress=last_percent,
                downloadedBytes=int(downloaded),
                totalBytes=int(total) if total else None,
                speed=human_size(int(speed)) + "/s" if speed else None,
                eta=human_duration(data.get("eta")) if data.get("eta") else None,
            )
        elif status == "finished":
            last_percent = max(last_percent, 99.0)
            progress(
                status="processing",
                progress=last_percent,
                speed=None,
                eta=None,
            )
        elif status == "error":
            raise AppError("DOWNLOAD_FAILED", "下载过程中断，请重试。", 502)

    def on_postprocessor(data: dict[str, Any]) -> None:
        if data.get("status") == "started":
            progress(status="processing", progress=99.0, speed=None, eta=None)

    opts = _base_opts(
        adapter,
        outtmpl=outtmpl,
        progress_hook=on_progress,
        postprocessor_hook=on_postprocessor,
        audio_only=audio_only,
    )
    opts["format"] = selector_for(tier)

    try:
        if checkpoint:
            checkpoint()
        progress(status="downloading", progress=0.0, speed=None, eta=None)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if isinstance(info, dict):
                info = _validate_info(info)
    except (DownloadPaused, DownloadCancelled):
        raise
    except AppError:
        raise
    except DownloadError as exc:
        raise _friendly_error(exc, adapter) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected download failure")
        raise _friendly_error(exc, adapter) from exc

    output = _find_output(directory)
    if output is None:
        raise AppError("NO_OUTPUT", "下载完成但没有找到文件，请重试。", 500)
    if output.stat().st_size <= 0:
        raise AppError("EMPTY_OUTPUT", "下载到的文件是空的，请重试。", 500)
    if output.stat().st_size > MAX_FILESIZE_BYTES:
        raise AppError("TOO_LARGE", "视频超过当前大小限制，暂时无法下载。", 413)

    progress(
        status="processing",
        progress=100.0,
        speed=None,
        eta=None,
        filename=output.name,
        filesize=output.stat().st_size,
    )
    return output, output.name
