from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any

from .library import (
    LibraryStore,
    absolute_path,
    now_iso,
    parse_frontmatter,
    relative_path,
    render_frontmatter,
)

_SUMMARY_RE = None
_ARTICLE_RE = None


def _replace_between(text: str, start: str, end: str, content: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    return pattern.sub(f"{start}\n{content.strip()}\n{end}", text, count=1)


def _article_body(article: str) -> str:
    text = (article or "").strip()
    text = re.sub(r"^#\s+.*\n+", "", text, count=1)
    lines = text.splitlines()
    while lines and lines[0].strip().startswith(">"):
        lines.pop(0)
    return "\n".join(lines).strip()


class NoteWriter:
    """Write one Markdown note while the summary job is running.

    The draft is valid Markdown from the start. Transcript text is appended as
    it is produced; summary and article replace marked placeholders. On success
    the draft is atomically renamed to the final repository filename.
    """

    def __init__(self, library: LibraryStore, note: dict[str, Any]) -> None:
        self.library = library
        self.note = note
        self.note_id = str(note["id"])
        self.title = str(note.get("title") or "未命名视频")
        self.draft_path = absolute_path(note.get("draftPath")) or (
            library.root / ".drafts" / f"{self.note_id}.md"
        )
        self.final_path = absolute_path(note.get("filePath")) or (
            library.root / f"{self.note_id}.md"
        )
        self._lock = threading.RLock()
        self._started = False

    def start(self) -> None:
        with self._lock:
            self.draft_path.parent.mkdir(parents=True, exist_ok=True)
            self.final_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "id": self.note_id,
                "title": self.title,
                "ai_summary": "",
                "source_url": self.note.get("sourceUrl") or "",
                "platform": self.note.get("platform") or "",
                "uploader": self.note.get("uploader") or "",
                "duration": int(self.note.get("duration") or 0),
                "duration_text": self.note.get("durationText") or "",
                "status": "processing",
                "transcript_source": self.note.get("transcriptSource") or "",
                "model": self.note.get("model") or "",
                "created_at": self.note.get("createdAt") or now_iso(),
                "updated_at": now_iso(),
                "tags": [],
            }
            body = self._initial_body()
            self.draft_path.write_text(
                render_frontmatter(data) + "\n" + body,
                encoding="utf-8",
            )
            self._started = True
            self.library.update(
                self.note_id,
                draft_path=relative_path(self.draft_path),
                status="processing",
                error="",
            )

    def _initial_body(self) -> str:
        source = self._source_line()
        return f"""# {self.title}

> **出处**：{source}
> 由 ClipDock 自动整理 · AI 生成，可能存在误差

## AI 摘要
<!-- SUMMARY_START -->
_正在生成摘要…_
<!-- SUMMARY_END -->

## 完整文案
<!-- ARTICLE_START -->
_正在生成完整文案…_
<!-- ARTICLE_END -->

## 原始转写
<details>
<summary>展开带时间戳的完整转写</summary>

"""

    def _source_line(self) -> str:
        platform = self.note.get("platform") or "视频"
        uploader = self.note.get("uploader") or ""
        duration = self.note.get("durationText") or ""
        url = self.note.get("sourceUrl") or ""
        parts = [part for part in (platform, uploader, duration) if part]
        label = " · ".join(parts)
        if url:
            return f"{label} · [原视频]({url})"
        return label or "出处未记录"

    def _read(self) -> str:
        try:
            return self.draft_path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def _write(self, text: str) -> None:
        self.draft_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.draft_path.with_suffix(".md.tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(self.draft_path)

    def append_transcript(self, text: str) -> None:
        if not text or not text.strip():
            return
        with self._lock:
            if not self._started:
                self.start()
            with self.draft_path.open("a", encoding="utf-8") as handle:
                handle.write(text.rstrip() + "\n")
                handle.flush()

    def set_transcript_source(self, source: str) -> None:
        with self._lock:
            self.note["transcriptSource"] = source
            self.library.update(self.note_id, transcript_source=source)

    def set_summary(self, summary: dict[str, Any]) -> None:
        with self._lock:
            text = self._read()
            if not text:
                return
            content: list[str] = []
            tldr = str(summary.get("tldr") or "").strip()
            if tldr:
                content.extend(["### 一句话总结", "", tldr, ""])
            points = [str(item).strip() for item in summary.get("keyPoints") or [] if str(item).strip()]
            if points:
                content.extend(["### 核心要点", ""])
                content.extend(f"- {item}" for item in points)
                content.append("")
            chapters = summary.get("chapters") or []
            if chapters:
                content.extend(["### 章节", ""])
                for chapter in chapters:
                    if not isinstance(chapter, dict):
                        continue
                    time = str(chapter.get("time") or "").strip()
                    title = str(chapter.get("title") or "").strip()
                    chapter_summary = str(chapter.get("summary") or "").strip()
                    content.append(f"- **{time} {title}**：{chapter_summary}".rstrip("："))
                content.append("")
            quotes = [str(item).strip() for item in summary.get("quotes") or [] if str(item).strip()]
            if quotes:
                content.extend(["### 关键引用", ""])
                content.extend(f"> {item}" for item in quotes)
                content.append("")
            keywords = [str(item).strip() for item in summary.get("keywords") or [] if str(item).strip()]
            if keywords:
                content.append("**关键词：** " + "、".join(keywords))
                content.append("")
            if not content:
                content = ["_AI 没有返回可用的结构化摘要。_"]
            text = _replace_between(text, "<!-- SUMMARY_START -->", "<!-- SUMMARY_END -->", "\n".join(content))
            self._write(text)
            self.note["aiSummary"] = tldr[:600]
            self.library.update(
                self.note_id,
                ai_summary=tldr[:600],
                status="processing",
            )

    def set_article(self, article: str) -> None:
        with self._lock:
            text = self._read()
            if not text:
                return
            body = _article_body(article) or "_AI 没有返回可用的完整文案。_"
            text = _replace_between(text, "<!-- ARTICLE_START -->", "<!-- ARTICLE_END -->", body)
            self._write(text)

    def set_article_error(self, message: str) -> None:
        with self._lock:
            text = self._read()
            if not text:
                return
            text = _replace_between(
                text,
                "<!-- ARTICLE_START -->",
                "<!-- ARTICLE_END -->",
                f"_完整文案生成失败：{message or '请稍后重试'}_",
            )
            self._write(text)

    def finalize(self) -> Path:
        with self._lock:
            text = self._read()
            if not text:
                raise FileNotFoundError("笔记草稿不存在")
            data, body = parse_frontmatter(text)
            data["status"] = "done"
            data["updated_at"] = now_iso()
            data["ai_summary"] = data.get("ai_summary") or self.note.get("aiSummary") or ""
            data["transcript_source"] = (
                self.note.get("transcriptSource") or data.get("transcript_source") or ""
            )
            data["model"] = self.note.get("model") or data.get("model") or ""
            if "</details>" not in body:
                body = body.rstrip() + "\n</details>\n"
            body = re.sub(r"<!-- (?:SUMMARY|ARTICLE)_(?:START|END) -->\n?", "", body)
            final_text = render_frontmatter(data) + "\n" + body.lstrip("\n")
            self.final_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.final_path.with_suffix(".md.tmp")
            temporary.write_text(final_text, encoding="utf-8")
            temporary.replace(self.final_path)
            self.draft_path.unlink(missing_ok=True)
            self.library.update(
                self.note_id,
                file_path=relative_path(self.final_path),
                draft_path="",
                status="done",
                file_size=self.final_path.stat().st_size,
                error="",
                updated_at=now_iso(),
            )
            return self.final_path

    def fail(self, message: str) -> None:
        with self._lock:
            text = self._read()
            if text:
                data, body = parse_frontmatter(text)
                data["status"] = "error"
                data["error"] = message
                data["updated_at"] = now_iso()
                self._write(render_frontmatter(data) + "\n" + body.lstrip("\n"))
            self.library.update(
                self.note_id,
                status="error",
                error=message,
                draft_path=relative_path(self.draft_path),
            )

    def content(self) -> str:
        path = self.final_path if self.final_path.is_file() else self.draft_path
        return path.read_text(encoding="utf-8") if path.is_file() else ""
