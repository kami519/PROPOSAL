from __future__ import annotations

from typing import Any


VIDEO_EXT_PREFERENCE = {"mp4": 3, "webm": 2, "mkv": 1}
AUDIO_EXT_PREFERENCE = {"m4a": 3, "mp3": 2, "opus": 1, "webm": 0}


def label_for_height(height: int | None) -> str:
    if not height:
        return "原画质"
    if height >= 2160:
        return "4K"
    if height >= 1440:
        return "2K"
    if height >= 1080:
        return "1080P"
    if height >= 720:
        return "720P"
    if height >= 480:
        return "480P"
    if height >= 360:
        return "360P"
    return f"{height}P"


def human_size(size: int | None) -> str | None:
    if not size or size <= 0:
        return None
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    index = 0
    while value >= 1024 and index < len(units) - 1:
        value /= 1024
        index += 1
    if index == 0:
        return f"{int(value)} {units[index]}"
    if value >= 100:
        return f"{value:.0f} {units[index]}"
    if value >= 10:
        return f"{value:.1f} {units[index]}"
    return f"{value:.2f} {units[index]}"


def human_duration(seconds: float | int | None) -> str:
    if not seconds or seconds <= 0:
        return "未知时长"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _size_of(fmt: dict[str, Any]) -> int:
    return int(fmt.get("filesize") or fmt.get("filesize_approx") or 0)


def _is_video(fmt: dict[str, Any]) -> bool:
    return fmt.get("vcodec") not in (None, "none") and bool(fmt.get("height"))


def _is_audio(fmt: dict[str, Any]) -> bool:
    return fmt.get("acodec") not in (None, "none") and fmt.get("vcodec") in (None, "none")


def _video_rank(fmt: dict[str, Any]) -> tuple:
    ext = fmt.get("ext") or ""
    vcodec = fmt.get("vcodec") or ""
    return (
        int(fmt.get("height") or 0),
        1 if vcodec.startswith("avc1") else 0,
        VIDEO_EXT_PREFERENCE.get(ext, 0),
        float(fmt.get("tbr") or 0),
        _size_of(fmt),
    )


def _audio_rank(fmt: dict[str, Any]) -> tuple:
    ext = fmt.get("ext") or ""
    return (
        AUDIO_EXT_PREFERENCE.get(ext, 0),
        float(fmt.get("abr") or fmt.get("tbr") or 0),
        _size_of(fmt),
    )


def build_formats(info: dict[str, Any]) -> tuple[list[dict[str, Any]], int | None]:
    """Build the small set of quality tiers the UI exposes.

    We never send raw format ids to the client. A tier maps to a stable yt-dlp
    selector on the server, which keeps the download path predictable.
    """

    raw_formats = info.get("formats") or []
    videos = [fmt for fmt in raw_formats if _is_video(fmt)]
    audios = [fmt for fmt in raw_formats if _is_audio(fmt)]

    if not videos:
        # Some direct-file extractors expose a single format or only a url.
        direct = any(fmt.get("url") for fmt in raw_formats) or bool(info.get("url"))
        if not direct:
            return [], None
        formats = [
            {
                "id": "720p",
                "label": "原文件",
                "sublabel": "直接下载",
                "height": None,
                "ext": "mp4",
                "size": None,
                "sizeText": None,
                "kind": "video",
            },
            {
                "id": "audio",
                "label": "仅音频",
                "sublabel": "MP3",
                "height": None,
                "ext": "mp3",
                "size": None,
                "sizeText": None,
                "kind": "audio",
            },
        ]
        return formats, None

    best_audio = max(audios, key=_audio_rank) if audios else None
    audio_size = _size_of(best_audio) if best_audio else 0
    max_height = max(int(fmt.get("height") or 0) for fmt in videos)

    def pick_video(max_allowed: int | None) -> dict[str, Any] | None:
        candidates = [
            fmt
            for fmt in videos
            if max_allowed is None or int(fmt.get("height") or 0) <= max_allowed
        ]
        return max(candidates, key=_video_rank) if candidates else None

    def video_size(fmt: dict[str, Any] | None) -> int | None:
        if fmt is None:
            return None
        size = _size_of(fmt)
        if fmt.get("acodec") in (None, "none"):
            size += audio_size
        return size or None

    free_height = min(720, max_height)
    free_video = pick_video(free_height)
    if free_video is None:
        free_video = pick_video(max_height)

    formats: list[dict[str, Any]] = []
    if free_video is not None:
        free_size = video_size(free_video)
        free_label = label_for_height(int(free_video.get("height") or 0))
        formats.append(
            {
                "id": "720p",
                "label": free_label,
                "sublabel": "MP4",
                "height": int(free_video.get("height") or 0) or None,
                "ext": "mp4",
                "size": free_size,
                "sizeText": human_size(free_size),
                "kind": "video",
            }
        )

    if max_height >= 1080:
        hd_video = pick_video(1080)
        if hd_video is not None:
            hd_size = video_size(hd_video)
            formats.append(
                {
                    "id": "1080p",
                    "label": label_for_height(int(hd_video.get("height") or 0)),
                    "sublabel": "高清 · MP4",
                    "height": int(hd_video.get("height") or 0) or None,
                    "ext": "mp4",
                    "size": hd_size,
                    "sizeText": human_size(hd_size),
                    "kind": "video",
                }
            )

    if max_height > 1080:
        best_video = pick_video(None)
        if best_video is not None:
            best_size = video_size(best_video)
            formats.append(
                {
                    "id": "best",
                    "label": label_for_height(int(best_video.get("height") or 0)),
                    "sublabel": "最高画质 · MP4",
                    "height": int(best_video.get("height") or 0) or None,
                    "ext": "mp4",
                    "size": best_size,
                    "sizeText": human_size(best_size),
                    "kind": "video",
                }
            )

    audio_size_value = audio_size or None
    formats.append(
        {
            "id": "audio",
            "label": "仅音频",
            "sublabel": "MP3 192k",
            "height": None,
            "ext": "mp3",
            "size": audio_size_value,
            "sizeText": human_size(audio_size_value),
            "kind": "audio",
        }
    )

    # De-duplicate by id while preserving order.
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in formats:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        unique.append(item)
    return unique, max_height


def selector_for(tier: str) -> str:
    if tier == "audio":
        return "bestaudio/best"
    if tier == "best":
        return "bestvideo+bestaudio/best"
    if tier == "1080p":
        height = 1080
    else:
        height = 720
    return (
        f"bestvideo[height<={height}][vcodec^=avc1]+bestaudio[ext=m4a]/"
        f"bestvideo[height<={height}]+bestaudio/"
        f"best[height<={height}]/best"
    )
