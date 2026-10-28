from __future__ import annotations

import hashlib
import html
import importlib.util
import json
import logging
import re
import shutil
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx
import numpy as np
import yt_dlp
from yt_dlp.utils import DownloadError

from .config import (
    CACHE_DIR,
    SUMMARY_API_BASE,
    SUMMARY_API_KEY,
    SUMMARY_ARTICLE_ENABLED,
    SUMMARY_ARTICLE_MAX_CHARS,
    SUMMARY_CACHE_TTL_SECONDS,
    SUMMARY_ENABLED,
    SUMMARY_MAX_CHARS,
    SUMMARY_MAX_DURATION_SECONDS,
    SUMMARY_MODEL,
    SUMMARY_TIMEOUT_SECONDS,
    SUMMARY_WORKERS,
    WHISPER_COMPUTE_TYPE,
    WHISPER_DEVICE,
    WHISPER_MODEL,
)
from .downloader import (
    FFMPEG_PATH,
    YdlLogger,
    _base_opts,
    _find_output,
    _friendly_error,
)
from .errors import AppError
from .formats import human_duration
from .library import LibraryStore, library_store
from .note_writer import NoteWriter

logger = logging.getLogger("clipdock.summary")

SUMMARY_DIR = CACHE_DIR / "summaries"
SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
SUMMARY_CACHE_DIR = CACHE_DIR / "summary-cache"
SUMMARY_CACHE_DIR.mkdir(parents=True, exist_ok=True)

SUMMARY_PROMPT_VERSION = "2026-10-28.1"
ARTICLE_PROMPT_VERSION = "2026-10-28.1"

_whisper_model = None
_whisper_lock = threading.Lock()
_transcribe_lock = threading.Lock()
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def _now() -> float:
    return time.time()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _summary_cache_key(url: str) -> str:
    return _digest(f"summary|{SUMMARY_MODEL}|{SUMMARY_PROMPT_VERSION}|{url}")


def _transcript_cache_key(url: str) -> str:
    return _digest(f"transcript|{WHISPER_MODEL}|{url}")


def _cache_dir(key: str) -> Path:
    path = SUMMARY_CACHE_DIR / key
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError as exc:
        logger.warning("写入总结缓存失败 %s: %s", path, exc)


def _fresh(path: Path) -> bool:
    try:
        return (
            path.is_file()
            and time.time() - path.stat().st_mtime <= SUMMARY_CACHE_TTL_SECONDS
        )
    except OSError:
        return False


def load_cached_transcript(url: str) -> dict[str, Any] | None:
    path = _cache_dir(_transcript_cache_key(url)) / "transcript.json"
    if not _fresh(path):
        return None
    data = _read_json(path)
    if not data or not str(data.get("transcript") or "").strip():
        return None
    return data


def save_cached_transcript(url: str, transcript: str, source: str) -> None:
    if not transcript.strip():
        return
    _write_json(
        _cache_dir(_transcript_cache_key(url)) / "transcript.json",
        {
            "url": url,
            "source": source,
            "transcript": transcript,
            "createdAt": int(_now()),
        },
    )


def load_cached_summary(url: str) -> dict[str, Any] | None:
    directory = _cache_dir(_summary_cache_key(url))
    summary_path = directory / "summary.json"
    if not _fresh(summary_path):
        return None
    summary = _read_json(summary_path)
    if not summary or not summary.get("result"):
        return None
    transcript = _read_json(directory / "transcript.json") or {}
    article = _read_json(directory / "article.json") or {}
    if article.get("promptVersion") != ARTICLE_PROMPT_VERSION:
        article = {}
    return {
        "result": summary.get("result"),
        "model": summary.get("model"),
        "transcript": transcript.get("transcript") or "",
        "transcriptSource": transcript.get("source"),
        "article": article.get("article") or "",
        "articleStatus": article.get("status") or "idle",
        "articleError": article.get("error"),
    }


def save_cached_summary(
    url: str,
    result: dict[str, Any],
    transcript: str,
    source: str | None,
) -> None:
    directory = _cache_dir(_summary_cache_key(url))
    _write_json(
        directory / "summary.json",
        {
            "url": url,
            "model": SUMMARY_MODEL,
            "promptVersion": SUMMARY_PROMPT_VERSION,
            "result": result,
            "createdAt": int(_now()),
        },
    )
    if transcript.strip():
        _write_json(
            directory / "transcript.json",
            {
                "source": source,
                "transcript": transcript,
                "createdAt": int(_now()),
            },
        )


def save_cached_article(url: str, article: str) -> None:
    _write_json(
        _cache_dir(_summary_cache_key(url)) / "article.json",
        {
            "status": "done",
            "article": article,
            "promptVersion": ARTICLE_PROMPT_VERSION,
            "createdAt": int(_now()),
        },
    )


def _clock(seconds: float | int | None) -> str:
    if not seconds or seconds <= 0:
        return "00:00"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _timestamp_to_seconds(value: str) -> float:
    value = value.strip().replace(",", ".")
    parts = value.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(parts[0])
    except (TypeError, ValueError):
        return 0.0


def _clean_subtitle_text(value: str) -> str:
    value = html.unescape(value)
    value = _TAG_RE.sub("", value)
    value = value.replace("&nbsp;", " ")
    return _SPACE_RE.sub(" ", value).strip()


def _parse_vtt_or_srt(text: str) -> str:
    entries: list[str] = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        time_line = next((line for line in lines if "-->" in line), None)
        if not time_line:
            continue
        start = time_line.split("-->", 1)[0].strip()
        seconds = _timestamp_to_seconds(start)
        content = " ".join(
            _clean_subtitle_text(line)
            for line in lines
            if "-->" not in line and not line.isdigit() and line.upper() != "WEBVTT"
        ).strip()
        if content:
            entries.append(f"[{_clock(seconds)}] {content}")
    return "\n".join(entries)


def _parse_json_subtitle(data: Any) -> str:
    entries: list[str] = []
    if isinstance(data, dict):
        body = data.get("body")
        if isinstance(body, list):
            for item in body:
                if not isinstance(item, dict):
                    continue
                content = _clean_subtitle_text(str(item.get("content") or ""))
                if content:
                    entries.append(f"[{_clock(item.get('from'))}] {content}")
        events = data.get("events")
        if isinstance(events, list):
            for event in events:
                if not isinstance(event, dict):
                    continue
                segs = event.get("segs") or []
                content = _clean_subtitle_text(
                    "".join(str(seg.get("utf8") or "") for seg in segs if isinstance(seg, dict))
                )
                if content:
                    entries.append(f"[{_clock((event.get('tStartMs') or 0) / 1000)}] {content}")
    return "\n".join(entries)


def parse_subtitle_file(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""
    if path.suffix.lower() == ".json":
        try:
            return _parse_json_subtitle(json.loads(text))
        except (TypeError, ValueError):
            return ""
    return _parse_vtt_or_srt(text)


def _subtitle_priority(path: Path) -> tuple[int, str]:
    name = path.name.lower()
    if "zh" in name or "中文" in name:
        return (0, name)
    if "en" in name:
        return (2, name)
    return (1, name)


def fetch_subtitle_text(url: str, directory: Path) -> str | None:
    """Download the first usable subtitle track without downloading the video."""

    directory.mkdir(parents=True, exist_ok=True)
    adapter = YdlLogger()
    opts = _base_opts(adapter, outtmpl=str(directory / "sub.%(id)s.%(ext)s"))
    opts.update(
        {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["zh-Hans", "zh-CN", "zh", "en", "ai-zh"],
            "subtitlesformat": "vtt/srt/best",
        }
    )
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
    except DownloadError as exc:
        logger.info("Subtitle extraction failed, falling back to audio: %s", str(exc)[:300])
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Subtitle extraction failed: %s", str(exc)[:300])
        return None

    files = [
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in {".vtt", ".srt", ".json", ".json3"}
    ]
    for path in sorted(files, key=_subtitle_priority):
        transcript = parse_subtitle_file(path)
        if len(transcript.strip()) >= 12:
            return transcript
    return None


def download_audio_for_summary(
    url: str,
    directory: Path,
    progress: Callable[..., None],
) -> Path:
    """Download only the audio stream for transcription.

    The public ``audio`` download tier extracts MP3 first, which is wasted work
    here: Whisper needs PCM and ffmpeg can decode m4a/webm directly. This keeps
    one transcode out of the slow path.
    """

    directory.mkdir(parents=True, exist_ok=True)
    adapter = YdlLogger()
    opts = _base_opts(adapter, outtmpl=str(directory / "audio.%(ext)s"))
    opts["format"] = "bestaudio/best"

    last_percent = 0.0

    def on_progress(data: dict[str, Any]) -> None:
        nonlocal last_percent
        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            downloaded = data.get("downloaded_bytes") or 0
            percent = 0.0
            if total:
                percent = max(0.0, min(98.0, downloaded / total * 100))
            last_percent = max(last_percent, percent)
            progress(status="downloading", progress=last_percent)
        elif status == "finished":
            progress(status="processing", progress=99.0)

    opts["progress_hooks"] = [on_progress]
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
    except DownloadError as exc:
        raise _friendly_error(exc, adapter) from exc
    except Exception as exc:  # noqa: BLE001 - map to a user-facing error
        raise _friendly_error(exc, adapter) from exc

    audio_suffixes = {".m4a", ".mp3", ".webm", ".opus", ".ogg", ".wav", ".aac", ".mp4"}
    candidates = [
        item
        for item in directory.iterdir()
        if item.is_file() and item.suffix.lower() in audio_suffixes and item.stat().st_size > 0
    ]
    path = max(candidates, key=lambda item: item.stat().st_size) if candidates else None
    if path is None:
        path = _find_output(directory)
    if path is None or path.stat().st_size <= 0:
        raise AppError("AUDIO_EMPTY", "没有提取到有效音频。", 422)
    return path


def _load_whisper_model():
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    if importlib.util.find_spec("faster_whisper") is None:
        raise AppError(
            "WHISPER_UNAVAILABLE",
            "本地转写组件未安装，暂时无法处理无字幕视频。",
            503,
        )
    with _whisper_lock:
        if _whisper_model is None:
            from faster_whisper import WhisperModel

            logger.info(
                "Loading Whisper model=%s device=%s compute=%s",
                WHISPER_MODEL,
                WHISPER_DEVICE,
                WHISPER_COMPUTE_TYPE,
            )
            _whisper_model = WhisperModel(
                WHISPER_MODEL,
                device=WHISPER_DEVICE,
                compute_type=WHISPER_COMPUTE_TYPE,
            )
    return _whisper_model


def _decode_audio(path: Path) -> np.ndarray:
    """Decode with ffmpeg instead of PyAV.

    faster-whisper 1.2.1 calls a PyAV API removed in PyAV 19 on Windows. Passing
    a float32 PCM array to Whisper avoids that incompatible decode path while
    still using the locally installed ffmpeg.
    """

    command = [
        FFMPEG_PATH,
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(path),
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "-ac",
        "1",
        "-ar",
        "16000",
        "pipe:1",
    ]
    proc = subprocess.run(command, capture_output=True, timeout=300)
    if proc.returncode != 0:
        logger.warning("ffmpeg decode failed: %s", proc.stderr.decode("utf-8", "replace")[:500])
        raise AppError("AUDIO_DECODE_FAILED", "音频解码失败，请稍后重试。", 500)
    samples = np.frombuffer(proc.stdout, dtype=np.int16)
    if samples.size == 0:
        raise AppError("AUDIO_EMPTY", "没有提取到有效音频。", 422)
    return samples.astype(np.float32) / 32768.0


def transcribe_audio(
    path: Path,
    progress: Callable[[float], None],
    on_segment: Callable[[str], None] | None = None,
) -> str:
    model = _load_whisper_model()
    audio = _decode_audio(path)
    duration = len(audio) / 16000
    with _transcribe_lock:
        segments, _info = model.transcribe(
            audio,
            language=None,
            vad_filter=True,
            beam_size=1,
            condition_on_previous_text=False,
        )
        entries: list[str] = []
        for segment in segments:
            text = _clean_subtitle_text(segment.text)
            if text:
                line = f"[{_clock(segment.start)}] {text}"
                entries.append(line)
                if on_segment is not None:
                    on_segment(line)
            if duration:
                progress(min(99.0, float(segment.end) / duration * 100))
    return "\n".join(entries)


def _chunk_text(text: str, size: int) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.splitlines():
        if current and current_len + len(line) + 1 > size:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks or [text]


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    # Models sometimes put a short preamble or trailing explanation around the
    # JSON. JSONDecoder.raw_decode lets us ignore that trailing text instead of
    # slicing from the first "{" to the last "}", which breaks when the model
    # emits a second object or an unclosed brace.
    decoder = json.JSONDecoder()
    candidates: list[dict[str, Any]] = []
    for match in list(re.finditer(r"\{", cleaned))[:80]:
        try:
            data, _end = decoder.raw_decode(cleaned[match.start() :])
        except ValueError:
            continue
        if isinstance(data, dict):
            candidates.append(data)

    if candidates:
        for data in candidates:
            if any(key in data for key in ("tldr", "keyPoints", "chapters")):
                return data
        return candidates[0]

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(cleaned[start : end + 1])
            if isinstance(data, dict):
                return data
        except ValueError:
            pass

    logger.warning(
        "Summary JSON parse failed: length=%s head=%r tail=%r",
        len(cleaned),
        cleaned[:400],
        cleaned[-400:],
    )
    raise AppError("SUMMARY_FORMAT_ERROR", "AI 返回的总结格式不正确，请重试。", 502)


def _chat(messages: list[dict[str, str]], max_tokens: int = 2200) -> str:
    if not SUMMARY_ENABLED:
        raise AppError(
            "SUMMARY_NOT_CONFIGURED",
            "AI 总结还没有配置模型密钥，请联系站点管理员。",
            503,
        )
    url = f"{SUMMARY_API_BASE}/chat/completions"
    if SUMMARY_API_BASE.endswith("/chat/completions"):
        url = SUMMARY_API_BASE
    try:
        with httpx.Client(timeout=SUMMARY_TIMEOUT_SECONDS) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {SUMMARY_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": SUMMARY_MODEL,
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": max_tokens,
                },
            )
    except httpx.HTTPError as exc:
        raise AppError("SUMMARY_API_ERROR", "AI 服务连接失败，请稍后重试。", 502) from exc

    if response.status_code >= 400:
        logger.warning("Summary API error %s: %s", response.status_code, response.text[:500])
        raise AppError("SUMMARY_API_ERROR", f"AI 服务返回错误（{response.status_code}），请稍后重试。", 502)
    try:
        payload = response.json()
        choice = payload["choices"][0]
        message = choice["message"]
        content = str(message.get("content") or "")
        if not content.strip():
            reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
            logger.warning(
                "Empty AI content: finish_reason=%s message_keys=%s reasoning_chars=%s",
                choice.get("finish_reason"),
                list(message.keys()),
                len(str(reasoning)),
            )
        return content
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise AppError("SUMMARY_API_ERROR", "AI 服务返回内容无法读取，请稍后重试。", 502) from exc


def _normalize_summary(data: dict[str, Any]) -> dict[str, Any]:
    def text(value: Any, limit: int = 1200) -> str:
        return str(value or "").strip()[:limit]

    def string_list(value: Any, limit: int = 12, item_limit: int = 300) -> list[str]:
        if not isinstance(value, list):
            return []
        return [text(item, item_limit) for item in value if text(item, item_limit)][:limit]

    chapters: list[dict[str, str]] = []
    raw_chapters = data.get("chapters")
    if isinstance(raw_chapters, list):
        for item in raw_chapters[:10]:
            if not isinstance(item, dict):
                continue
            title = text(item.get("title"), 120)
            summary = text(item.get("summary"), 500)
            if title or summary:
                chapters.append(
                    {
                        "time": text(item.get("time"), 20) or "00:00",
                        "title": title or "未命名章节",
                        "summary": summary,
                    }
                )

    tldr = text(data.get("tldr") or data.get("summary") or data.get("oneSentence"), 500)
    key_points = string_list(data.get("keyPoints") or data.get("key_points"), 10, 400)
    if not tldr and key_points:
        tldr = key_points[0]
    if not tldr:
        raise AppError("SUMMARY_FORMAT_ERROR", "AI 没有返回有效的总结内容，请重试。", 502)

    return {
        "tldr": tldr,
        "keyPoints": key_points,
        "chapters": chapters,
        "quotes": string_list(data.get("quotes"), 5, 500),
        "keywords": string_list(data.get("keywords"), 12, 60),
        "suitableFor": text(data.get("suitableFor") or data.get("suitable_for"), 300),
    }


def _fallback_summary(context: str) -> dict[str, Any] | None:
    """Last-resort summary when the JSON output stays malformed.

    The user would otherwise see a red error after several minutes of
    transcription. A one-sentence summary is less useful than the full
    structured result, but it keeps the result actionable.
    """

    try:
        text = _chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是中文视频总结助手。只根据给定内容，用不超过 80 字的一句话"
                        "概括视频讲了什么；不要 JSON，不要标题，不要解释。"
                    ),
                },
                {"role": "user", "content": context[:12_000]},
            ],
            max_tokens=300,
        )
    except Exception:  # noqa: BLE001 - fallback must not mask the original error
        logger.exception("Fallback summary failed")
        return None
    tldr = _clean_subtitle_text(text).strip()
    if not tldr:
        return None
    return {
        "tldr": tldr[:300],
        "keyPoints": [],
        "chapters": [],
        "quotes": [],
        "keywords": [],
        "suitableFor": "",
        "fallback": True,
    }


def summarize_transcript(
    transcript: str,
    progress: Callable[[float], None],
) -> dict[str, Any]:
    if len(transcript) > SUMMARY_MAX_CHARS:
        transcript = transcript[:SUMMARY_MAX_CHARS] + "\n[... 后文因长度限制被截断 ...]"

    chunks = _chunk_text(transcript, 12_000)
    context = transcript
    if len(chunks) > 1:
        notes: list[str] = []
        for index, chunk in enumerate(chunks[:4]):
            progress(20 + index * 12)
            notes.append(
                _chat(
                    [
                        {
                            "role": "system",
                            "content": "你是视频字幕整理助手。只提取片段中的事实、观点、关键时间点，用简洁中文输出，不要编造。",
                        },
                        {"role": "user", "content": f"片段 {index + 1}：\n{chunk}"},
                    ],
                    max_tokens=2500,
                )
            )
        context = "分段笔记：\n" + "\n\n".join(notes)
        if len(chunks) > 4:
            context += "\n\n[后续片段已省略]"

    progress(70)
    prompt = f"""你是中文视频内容总结助手。请只根据下面提供的字幕/转写内容生成总结，不要补充未出现的信息。

只输出一个完整、可解析的 JSON 对象，不要 Markdown 代码块、不要解释、不要思考过程。JSON 必须闭合，结构如下：
{{
  "tldr": "一句话总结，80 字以内",
  "keyPoints": ["3-5 条核心要点，每条不超过 80 字"],
  "chapters": [{{"time": "00:00", "title": "章节标题", "summary": "章节内容，80 字以内"}}],
  "quotes": ["0-2 条原文关键引用"],
  "keywords": ["5-8 个关键词"],
  "suitableFor": "一句话说明适合谁看"
}}

要求：
- 章节按时间顺序，3-6 个；时间尽量使用字幕中的时间戳
- 保留视频的核心观点、结论和重要事实
- 如果内容不足，可以少写，但不要编造
- 全部使用中文
- 宁可少写几条，也要保证 JSON 完整闭合

字幕/转写内容：
{context}
"""
    raw = _chat(
        [
            {
                "role": "system",
                "content": "你只输出合法 JSON，不输出解释、前后缀或代码块。",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=6000,
    )
    try:
        result = _normalize_summary(_extract_json(raw))
    except AppError as parse_error:
        logger.warning("Summary JSON invalid; attempting repair")
        try:
            repaired = _chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是 JSON 修复器。只输出一个完整、合法的 JSON 对象，"
                            "不要 Markdown 代码块、不要解释。字段为 tldr、keyPoints、"
                            "chapters、quotes、keywords、suitableFor；缺失内容用空数组或空字符串，"
                            "不要编造。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": "请修复下面这段视频总结输出：\n\n" + raw[:12_000],
                    },
                ],
                max_tokens=6000,
            )
            result = _normalize_summary(_extract_json(repaired))
        except AppError:
            fallback = _fallback_summary(context)
            if fallback is None:
                raise parse_error
            result = fallback

    progress(95)
    result["model"] = SUMMARY_MODEL
    result["generatedAt"] = int(_now())
    return result


def _clean_article(text: str) -> str:
    value = text.strip()
    value = re.sub(r"^```(?:markdown|md)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value)
    value = re.sub(r"^(好的|当然|以下是|下面是)[^\n]*\n+", "", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def write_article(
    transcript: str,
    summary: dict[str, Any],
    title: str,
    progress: Callable[[float], None],
) -> str:
    """把完整转写整理成可读的 Markdown 文章。

    与总结分开：总结回答“讲了什么”，整理稿保留“完整内容”，供后续阅读、
    复制和导出。长视频分段整理，避免一次生成把上下文和输出都撑爆。
    """

    if not SUMMARY_ARTICLE_ENABLED:
        raise AppError(
            "ARTICLE_DISABLED",
            "完整文案整理没有启用。",
            503,
        )
    transcript = (transcript or "").strip()
    if len(transcript) < 12:
        raise AppError("NO_SPEECH", "没有可整理的转写内容。", 422)
    if len(transcript) > SUMMARY_ARTICLE_MAX_CHARS:
        transcript = (
            transcript[:SUMMARY_ARTICLE_MAX_CHARS]
            + "\n\n[后文因长度限制未整理]"
        )

    chapters = summary.get("chapters") or []
    chapter_hint = "；".join(
        f"{item.get('time', '')} {item.get('title', '')}".strip()
        for item in chapters
        if isinstance(item, dict)
    )
    intro = (
        f"视频标题：{title}\n"
        f"章节参考：{chapter_hint or '无'}\n\n"
        "下面是带时间戳的字幕/语音转写：\n\n"
    )
    chunks = _chunk_text(transcript, 9_000)
    if len(chunks) == 1:
        prompt = (
            intro
            + chunks[0]
            + "\n\n请输出整理后的完整文章。"
        )
        raw = _chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是中文视频文案整理助手。把转写整理成可读的 Markdown 文章："
                        "按内容分节并使用 ## 小标题；合并碎句、补全标点；"
                        "删除口头禅、重复和无意义语气词；保留事实、数字、术语、结论和例子；"
                        "不要编造原文没有的信息；不要输出代码块或额外解释。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=8000,
        )
        if not raw.strip():
            logger.warning("Article single-pass returned empty content")
        body = _clean_article(raw)
    else:
        parts: list[str] = []
        for index, chunk in enumerate(chunks[:3]):
            progress(8 + index * 26)
            raw = _chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是中文视频文案整理助手。只整理下面这一段转写，"
                            "不要写全片总结，也不要重复上一段；按内容分节并使用 ## 小标题；"
                            "合并碎句、补全标点；删除口头禅和重复；保留事实、数字、术语和例子；"
                            "不要编造；只输出 Markdown 正文。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"{intro}第 {index + 1}/{min(len(chunks), 3)} 段：\n\n{chunk}",
                    },
                ],
                max_tokens=6000,
            )
            if not raw.strip():
                logger.warning("Article chunk %s returned empty content", index + 1)
            parts.append(_clean_article(raw))
        body = "\n\n".join(part for part in parts if part)
        if len(chunks) > 3:
            body += "\n\n> 后文因长度限制未整理。"

    if not body.strip():
        raise AppError("ARTICLE_FORMAT_ERROR", "AI 没有返回可用的整理稿，请重试。", 502)

    header = f"# {title.strip() or '视频整理稿'}\n\n"
    tldr = str(summary.get("tldr") or "").strip()
    if tldr:
        header += f"> {tldr}\n\n"
    header += "> 根据视频字幕/语音转写由 AI 整理，可能存在误差；请以原视频为准。\n\n"
    progress(96)
    return header + body.strip()


@dataclass
class SummaryJob:
    id: str
    url: str
    directory: Path
    title: str = "未命名视频"
    thumbnail: str | None = None
    platform: str | None = None
    duration: int = 0
    status: str = "queued"
    stage: str = "queued"
    progress: float = 0.0
    transcript_source: str | None = None
    transcript: str | None = None
    result: dict[str, Any] | None = None
    article: str | None = None
    article_status: str = "idle"
    article_progress: float = 0.0
    article_error: str | None = None
    error: str | None = None
    error_code: str | None = None
    note_id: str | None = None
    note_writer: NoteWriter | None = None
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    future: Any = None
    article_future: Any = None

    def public(self) -> dict[str, Any]:
        result = self.result
        return {
            "id": self.id,
            "status": self.status,
            "stage": self.stage,
            "progress": round(self.progress, 1),
            "title": self.title,
            "thumbnail": self.thumbnail,
            "platform": self.platform,
            "duration": self.duration,
            "transcriptSource": self.transcript_source,
            "transcriptAvailable": bool(self.transcript and self.transcript.strip()),
            "transcriptChars": len(self.transcript or ""),
            "result": result,
            "articleStatus": self.article_status,
            "articleProgress": round(self.article_progress, 1),
            "articleChars": len(self.article or ""),
            "articleError": self.article_error,
            "noteId": self.note_id,
            "error": self.error,
            "errorCode": self.error_code,
            "createdAt": int(self.created_at),
            "updatedAt": int(self.updated_at),
        }


class SummaryStore:
    def __init__(self, library: LibraryStore | None = None) -> None:
        self._jobs: dict[str, SummaryJob] = {}
        self._lock = threading.RLock()
        self.library = library or library_store
        self._executor = ThreadPoolExecutor(
            max_workers=SUMMARY_WORKERS, thread_name_prefix="clipdock-summary"
        )
        # 总结先返回，整理稿在后台继续生成；不要占住总结线程。
        self._article_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="clipdock-article"
        )

    def _prepare_note(self, job: SummaryJob, uploader: str | None) -> None:
        note = self.library.prepare_note(
            {
                "title": job.title,
                "source_url": job.url,
                "platform": job.platform,
                "uploader": uploader or "",
                "duration": job.duration,
                "duration_text": human_duration(job.duration),
                "thumbnail": job.thumbnail or "",
                "model": SUMMARY_MODEL,
            }
        )
        writer = NoteWriter(self.library, note)
        writer.start()
        job.note_id = str(note["id"])
        job.note_writer = writer

    def _finish_cached_note(
        self,
        job: SummaryJob,
        cached: dict[str, Any],
    ) -> None:
        writer = job.note_writer
        if writer is None:
            return
        transcript = str(cached.get("transcript") or "")
        source = cached.get("transcriptSource")
        if transcript.strip():
            writer.append_transcript(transcript)
            writer.set_transcript_source(str(source or "cache"))
        result = cached.get("result")
        if result:
            writer.set_summary(result)
        article = cached.get("article")
        if article:
            writer.set_article(str(article))
            writer.finalize()
            job.article_status = "done"
            job.article_progress = 100.0
        elif not SUMMARY_ARTICLE_ENABLED:
            writer.finalize()

    def create(
        self,
        *,
        url: str,
        title: str | None,
        thumbnail: str | None,
        platform: str | None,
        duration: int,
        uploader: str | None = None,
    ) -> dict[str, Any]:
        if not SUMMARY_ENABLED:
            raise AppError(
                "SUMMARY_NOT_CONFIGURED",
                "AI 总结还没有配置模型密钥，请联系站点管理员。",
                503,
            )
        if duration and duration > SUMMARY_MAX_DURATION_SECONDS:
            raise AppError(
                "SUMMARY_TOO_LONG",
                f"AI 总结目前只支持 {SUMMARY_MAX_DURATION_SECONDS // 60} 分钟以内的视频。",
                422,
            )

        job = SummaryJob(
            id=uuid.uuid4().hex,
            url=url,
            directory=SUMMARY_DIR / uuid.uuid4().hex,
            title=(title or "未命名视频")[:240],
            thumbnail=thumbnail[:2048] if thumbnail else None,
            platform=(platform or "视频平台")[:80],
            duration=duration,
        )
        try:
            self._prepare_note(job, uploader)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Create note failed")
            raise AppError("NOTE_STORAGE_ERROR", "无法创建 Markdown 笔记。", 500) from exc

        cached = load_cached_summary(url)
        if cached:
            job.status = "done"
            job.stage = "done"
            job.progress = 100.0
            job.result = cached.get("result")
            job.transcript = cached.get("transcript") or ""
            job.transcript_source = cached.get("transcriptSource")
            job.article = cached.get("article") or None
            job.article_status = cached.get("articleStatus") or "idle"
            job.article_error = cached.get("articleError")
            if job.article:
                job.article_progress = 100.0
            self._finish_cached_note(job, cached)
            with self._lock:
                self._jobs[job.id] = job
            if not job.article and SUMMARY_ARTICLE_ENABLED:
                self._start_article(job)
            return job.public()

        transcript_cache = load_cached_transcript(url)
        if transcript_cache:
            job.transcript = transcript_cache.get("transcript") or ""
            job.transcript_source = transcript_cache.get("source")

        try:
            job.directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AppError("SUMMARY_STORAGE_ERROR", "无法创建总结临时目录。", 500) from exc

        with self._lock:
            self._jobs[job.id] = job
            job.future = self._executor.submit(self._run, job)
        return job.public()

    def _require(self, job_id: str) -> SummaryJob:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise AppError("SUMMARY_NOT_FOUND", "总结任务不存在或已过期。", 404)
            return job

    def _update(self, job: SummaryJob, **values: Any) -> None:
        with self._lock:
            for key, value in values.items():
                setattr(job, key, value)
            job.updated_at = _now()

    def _transcript_for(
        self,
        job: SummaryJob,
        on_segment: Callable[[str], None] | None = None,
    ) -> tuple[str, str]:
        def emit(text: str) -> None:
            if on_segment is not None and text:
                try:
                    on_segment(text)
                except Exception:  # noqa: BLE001 - writing a draft must not break the job
                    logger.exception("Transcript append failed for %s", job.id)

        if job.transcript and job.transcript.strip():
            emit(job.transcript)
            return job.transcript, job.transcript_source or "cache"

        cached = load_cached_transcript(job.url)
        if cached:
            transcript = str(cached.get("transcript") or "")
            source = str(cached.get("source") or "cache")
            if transcript.strip():
                self._update(
                    job,
                    transcript=transcript,
                    transcript_source=source,
                    stage="fetching_subtitles",
                    progress=20.0,
                )
                emit(transcript)
                return transcript, source

        self._update(job, status="processing", stage="fetching_subtitles", progress=5.0)
        transcript = fetch_subtitle_text(job.url, job.directory)
        if transcript:
            self._update(job, transcript_source="subtitle", progress=20.0)
            save_cached_transcript(job.url, transcript, "subtitle")
            emit(transcript)
            return transcript, "subtitle"

        self._update(job, stage="downloading_audio", progress=18.0)
        audio = download_audio_for_summary(
            job.url,
            job.directory,
            lambda **values: self._update(
                job,
                stage="downloading_audio",
                progress=min(40.0, 18 + (float(values.get("progress") or 0) * 0.22)),
            ),
        )
        self._update(job, stage="transcribing", progress=42.0)
        transcript = transcribe_audio(
            audio,
            lambda value: self._update(
                job, stage="transcribing", progress=42 + (value * 0.35)
            ),
            on_segment=emit,
        )
        self._update(job, transcript_source="audio", progress=78.0)
        save_cached_transcript(job.url, transcript, "audio")
        return transcript, "audio"

    def _start_article(self, job: SummaryJob) -> None:
        if not SUMMARY_ARTICLE_ENABLED or not job.transcript or not job.result:
            return
        with self._lock:
            if job.article_status in {"processing", "done"}:
                return
            job.article_status = "processing"
            job.article_progress = max(1.0, job.article_progress)
            job.article_error = None
            job.article_future = self._article_executor.submit(self._run_article, job)

    def _run(self, job: SummaryJob) -> None:
        writer = job.note_writer
        try:
            on_segment = writer.append_transcript if writer is not None else None
            transcript, source = self._transcript_for(job, on_segment=on_segment)
            if not transcript.strip():
                raise AppError("NO_SPEECH", "没有提取到可总结的字幕或语音内容。", 422)
            if writer is not None:
                writer.set_transcript_source(source)

            self._update(
                job,
                status="processing",
                transcript=transcript,
                transcript_source=source,
                stage="summarizing",
                progress=82.0,
            )
            result = summarize_transcript(
                transcript,
                lambda value: self._update(
                    job, stage="summarizing", progress=82 + (value * 0.15)
                ),
            )
            if writer is not None:
                writer.set_summary(result)
            save_cached_summary(job.url, result, transcript, source)
            if SUMMARY_ARTICLE_ENABLED:
                self._update(
                    job,
                    status="done",
                    stage="done",
                    progress=100.0,
                    result=result,
                    error=None,
                    error_code=None,
                )
                self._start_article(job)
            else:
                # 没有整理稿时，先把 Markdown 落盘完成，再对外报 done。
                if writer is not None:
                    writer.finalize()
                self._update(
                    job,
                    status="done",
                    stage="done",
                    progress=100.0,
                    result=result,
                    error=None,
                    error_code=None,
                )
        except AppError as exc:
            logger.warning("Summary %s failed: %s (%s)", job.id, exc.message, exc.code)
            if writer is not None:
                writer.fail(exc.message)
            self._update(job, status="error", error=exc.message, error_code=exc.code)
        except Exception:  # noqa: BLE001
            logger.exception("Summary %s crashed", job.id)
            if writer is not None:
                writer.fail("AI 总结失败，请稍后重试。")
            self._update(
                job,
                status="error",
                error="AI 总结失败，请稍后重试。",
                error_code="SUMMARY_FAILED",
            )
        finally:
            shutil.rmtree(job.directory, ignore_errors=True)

    def _run_article(self, job: SummaryJob) -> None:
        writer = job.note_writer
        if not job.transcript or not job.result:
            message = "没有可整理的转写内容。"
            if writer is not None:
                writer.set_article_error(message)
                self.library.update(job.note_id or "", status="done", error=message)
            self._update(job, article_status="error", article_error=message)
            return
        try:
            self._update(
                job,
                article_status="processing",
                article_progress=3.0,
                article_error=None,
            )
            article = write_article(
                job.transcript,
                job.result,
                job.title,
                lambda value: self._update(
                    job,
                    article_progress=max(3.0, min(99.0, value)),
                ),
            )
            if writer is not None:
                writer.set_article(article)
                writer.finalize()
            self._update(
                job,
                article=article,
                article_status="done",
                article_progress=100.0,
                article_error=None,
            )
            save_cached_article(job.url, article)
        except AppError as exc:
            logger.warning("Article %s failed: %s (%s)", job.id, exc.message, exc.code)
            if writer is not None:
                writer.set_article_error(exc.message)
                if job.note_id:
                    self.library.update(
                        job.note_id,
                        status="done",
                        error=exc.message,
                    )
            self._update(
                job,
                article_status="error",
                article_error=exc.message,
                article_progress=0.0,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Article %s crashed", job.id)
            message = "整理稿生成失败，请稍后重试。"
            if writer is not None:
                writer.set_article_error(message)
                if job.note_id:
                    self.library.update(job.note_id, status="done", error=message)
            self._update(
                job,
                article_status="error",
                article_error=message,
                article_progress=0.0,
            )

    def get(self, job_id: str) -> dict[str, Any]:
        return self._require(job_id).public()

    def request_article(self, job_id: str) -> dict[str, Any]:
        job = self._require(job_id)
        if job.status != "done" or not job.result:
            raise AppError("SUMMARY_NOT_READY", "先等总结完成，再生成整理稿。", 409)
        if not SUMMARY_ARTICLE_ENABLED:
            raise AppError("ARTICLE_DISABLED", "完整文案整理没有启用。", 503)
        if job.article_status != "done":
            with self._lock:
                job.article_status = "idle"
                job.article_error = None
            self._start_article(job)
        return job.public()

    def article(self, job_id: str) -> dict[str, Any]:
        job = self._require(job_id)
        return {
            "id": job.id,
            "status": job.article_status,
            "progress": round(job.article_progress, 1),
            "article": job.article,
            "chars": len(job.article or ""),
            "error": job.article_error,
        }

    def transcript(self, job_id: str) -> dict[str, Any]:
        job = self._require(job_id)
        return {
            "id": job.id,
            "source": job.transcript_source,
            "chars": len(job.transcript or ""),
            "transcript": job.transcript or "",
        }

    def count(self) -> int:
        with self._lock:
            return len(self._jobs)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._article_executor.shutdown(wait=False, cancel_futures=True)


def whisper_available() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


summary_store = SummaryStore()
