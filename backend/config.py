from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
load_dotenv(BASE_DIR / ".env")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_path(name: str) -> Path | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (BASE_DIR / path).resolve()
    return path


CACHE_DIR = _env_path("CLIPDOCK_CACHE_DIR") or (BASE_DIR / "data" / "cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
JOBS_DIR = CACHE_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

# Persistent Markdown note repository. The SQLite file is only a rebuildable
# index; the .md files are the source of truth.
LIBRARY_DIR = _env_path("CLIPDOCK_LIBRARY_DIR") or (BASE_DIR / "data" / "library")
LIBRARY_DB = _env_path("CLIPDOCK_LIBRARY_DB") or (BASE_DIR / "data" / "library.sqlite3")
LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
(LIBRARY_DIR / ".drafts").mkdir(parents=True, exist_ok=True)
(LIBRARY_DIR / ".trash").mkdir(parents=True, exist_ok=True)
LIBRARY_TRASH_TTL_DAYS = max(1, _env_int("LIBRARY_TRASH_TTL_DAYS", 7))

APP_NAME = "ClipDock"
APP_VERSION = "0.1.0"

# Download guards. These are deliberately conservative for a demo deployment.
MAX_DURATION_SECONDS = _env_int("MAX_DURATION_SECONDS", 2 * 60 * 60)
MAX_FILESIZE_BYTES = _env_int("MAX_FILESIZE_BYTES", 4 * 1024 * 1024 * 1024)
MIN_FREE_BYTES = _env_int("MIN_FREE_BYTES", 512 * 1024 * 1024)
DOWNLOAD_WORKERS = max(1, _env_int("DOWNLOAD_WORKERS", 2))
# 0 disables the limit. A small cloud instance may only afford one active
# video download at a time; extra jobs stay queued.
DOWNLOAD_CONCURRENCY = max(0, _env_int("DOWNLOAD_CONCURRENCY", 0))
MAX_JOBS = max(4, _env_int("MAX_JOBS", 60))
JOB_TTL_SECONDS = max(300, _env_int("JOB_TTL_SECONDS", 30 * 60))
CLEANUP_INTERVAL_SECONDS = max(30, _env_int("CLEANUP_INTERVAL_SECONDS", 60))

# Optional yt-dlp runtime settings.
COOKIES_FILE = _env_path("YTDLP_COOKIES")
PROXY = os.getenv("YTDLP_PROXY", "").strip() or None

ALLOWED_FORMATS = {"720p", "1080p", "best", "audio"}

# AI summary. The summary endpoint is disabled until an OpenAI-compatible key
# is configured. Subtitle-first is cheap; audio fallback uses local Whisper.
SUMMARY_API_BASE = os.getenv("SUMMARY_API_BASE", "https://api.deepseek.com/v1").rstrip("/")
SUMMARY_API_KEY = os.getenv("SUMMARY_API_KEY", "").strip()
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", "deepseek-flash").strip()
# Summary jobs advance through network-heavy and CPU-heavy stages. Keep the
# task-level concurrency separate from the Whisper and LLM limits so a slow
# local transcription cannot block every other summary.
SUMMARY_WORKERS = max(1, _env_int("SUMMARY_WORKERS", 3))
SUMMARY_TRANSCRIBE_WORKERS = max(1, _env_int("SUMMARY_TRANSCRIBE_WORKERS", 1))
SUMMARY_LLM_CONCURRENCY = max(1, _env_int("SUMMARY_LLM_CONCURRENCY", 4))
SUMMARY_ARTICLE_WORKERS = max(1, _env_int("SUMMARY_ARTICLE_WORKERS", 2))
SUMMARY_QUEUE_MAX = max(1, _env_int("SUMMARY_QUEUE_MAX", 20))
SUMMARY_JOB_TTL_SECONDS = max(3600, _env_int("SUMMARY_JOB_TTL_SECONDS", 24 * 60 * 60))
SUMMARY_MAX_JOBS = max(20, _env_int("SUMMARY_MAX_JOBS", 100))
SUMMARY_LLM_RETRIES = max(0, _env_int("SUMMARY_LLM_RETRIES", 2))
SUMMARY_LLM_BACKOFF_SECONDS = max(0.1, _env_float("SUMMARY_LLM_BACKOFF_SECONDS", 1.5))
SUMMARY_PERSIST_JOBS = os.getenv("SUMMARY_PERSIST_JOBS", "true").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
SUMMARY_MAX_DURATION_SECONDS = max(60, _env_int("SUMMARY_MAX_DURATION_SECONDS", 45 * 60))
SUMMARY_MAX_CHARS = max(2000, _env_int("SUMMARY_MAX_CHARS", 30_000))
SUMMARY_TIMEOUT_SECONDS = max(10, _env_int("SUMMARY_TIMEOUT_SECONDS", 120))
# 完整文案：先用转写结果做 AI 整理；默认开启，可在 .env 关掉。
SUMMARY_ARTICLE_ENABLED = os.getenv("SUMMARY_ARTICLE_ENABLED", "true").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
SUMMARY_ARTICLE_MAX_CHARS = max(4000, _env_int("SUMMARY_ARTICLE_MAX_CHARS", 24_000))
SUMMARY_CACHE_TTL_SECONDS = max(3600, _env_int("SUMMARY_CACHE_TTL_SECONDS", 30 * 24 * 60 * 60))
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small").strip() or "small"
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu").strip() or "cpu"
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8").strip() or "int8"
SUMMARY_ENABLED = bool(SUMMARY_API_KEY and SUMMARY_API_BASE and SUMMARY_MODEL)

PLATFORM_NAMES = {
    "bilibili": "B站",
    "bilibili:bangumi": "B站番剧",
    "douyin": "抖音",
    "youtube": "YouTube",
    "tiktok": "TikTok",
    "xiaohongshu": "小红书",
    "instagram": "Instagram",
    "twitter": "X",
    "vimeo": "Vimeo",
    "kuaishou": "快手",
    "weibo": "微博",
    "zhihu": "知乎",
    "netease": "网易云音乐",
    "ximalaya": "喜马拉雅",
    "twitch": "Twitch",
    "facebook": "Facebook",
    "reddit": "Reddit",
}
