from __future__ import annotations

import json
import re
import shutil
import sqlite3
import threading
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator

from .config import (
    BASE_DIR,
    CACHE_DIR,
    LIBRARY_DIR,
    LIBRARY_DB,
    LIBRARY_TRASH_TTL_DAYS,
)

_SAFE_NAME_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff._-]+")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def note_id() -> str:
    return "note_" + uuid.uuid4().hex[:12]


def slugify(title: str, limit: int = 40) -> str:
    text = _SAFE_NAME_RE.sub("-", (title or "").strip())
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    if len(text) > limit:
        text = text[:limit].rstrip("-._")
    return text or "note"


def relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(BASE_DIR.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def absolute_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else (BASE_DIR / path)


def _yaml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return json.dumps(str(value or ""), ensure_ascii=False)


def render_frontmatter(data: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in data.items():
        if value is None:
            continue
        lines.append(f"{key}: {_yaml_value(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    end = None
    for index in range(1, min(len(lines), 120)):
        if lines[index].strip() == "---":
            end = index
            break
    if end is None:
        return {}, text
    data: dict[str, Any] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, raw = line.split(":", 1)
        key = key.strip()
        raw = raw.strip()
        if not key:
            continue
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            value = raw.strip('"').strip("'")
        data[key] = value
    body = "\n".join(lines[end + 1 :])
    return data, body


def strip_frontmatter(text: str) -> str:
    return parse_frontmatter(text or "")[1]


def _row_to_public(row: sqlite3.Row) -> dict[str, Any]:
    file_path = row["file_path"] or ""
    return {
        "id": row["id"],
        "title": row["title"] or "",
        "aiSummary": row["ai_summary"] or "",
        "sourceUrl": row["source_url"] or "",
        "platform": row["platform"] or "",
        "uploader": row["uploader"] or "",
        "duration": row["duration"] or 0,
        "durationText": row["duration_text"] or "",
        "status": row["status"] or "processing",
        "transcriptSource": row["transcript_source"] or "",
        "model": row["model"] or "",
        "createdAt": row["created_at"] or "",
        "updatedAt": row["updated_at"] or "",
        "fileSize": row["file_size"] or 0,
        "error": row["error"] or "",
        "fileName": Path(file_path).name if file_path else "",
        "filePath": file_path,
        "trashed": row["status"] == "trashed",
    }


class LibraryStore:
    """SQLite index for the Markdown note repository.

    Markdown files are the source of truth. If the database is deleted, call
    ``rebuild_from_files()`` (also done automatically when the table is empty).
    """

    def __init__(self, db_path: Path | str | None = None, root: Path | None = None) -> None:
        self.db_path = Path(db_path or LIBRARY_DB)
        self.root = Path(root or LIBRARY_DIR)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()
        self._rebuild_if_empty()
        # Jobs live in memory; a processing row left after a restart can never
        # finish on its own. Mark it as interrupted so the user can retry.
        with self._connect() as connection:
            connection.execute(
                "UPDATE notes SET status='error', error=?, updated_at=? WHERE status='processing'",
                ("上次生成中断，请重新生成", now_iso()),
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _init_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    file_path TEXT NOT NULL DEFAULT '',
                    draft_path TEXT,
                    source_url TEXT,
                    platform TEXT,
                    uploader TEXT,
                    duration INTEGER DEFAULT 0,
                    duration_text TEXT,
                    thumbnail TEXT,
                    ai_summary TEXT,
                    status TEXT NOT NULL DEFAULT 'processing',
                    transcript_source TEXT,
                    model TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    file_size INTEGER DEFAULT 0,
                    error TEXT,
                    trash_path TEXT,
                    deleted_at TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_notes_source
                    ON notes(source_url) WHERE source_url IS NOT NULL AND source_url <> '';
                CREATE INDEX IF NOT EXISTS idx_notes_updated
                    ON notes(updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_notes_status
                    ON notes(status);
                """
            )

    def _rebuild_if_empty(self) -> None:
        with self._connect() as connection:
            count = connection.execute("SELECT COUNT(*) AS n FROM notes").fetchone()["n"]
        if count == 0:
            self.rebuild_from_files()

    def get(self, note_id_value: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM notes WHERE id = ?", (note_id_value,)
            ).fetchone()
        return _row_to_public(row) if row else None

    def raw(self, note_id_value: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM notes WHERE id = ?", (note_id_value,)
            ).fetchone()

    def find_by_source(self, source_url: str) -> dict[str, Any] | None:
        if not source_url:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM notes WHERE source_url = ?", (source_url,)
            ).fetchone()
        return _row_to_public(row) if row else None

    def prepare_note(self, meta: dict[str, Any]) -> dict[str, Any]:
        source_url = str(meta.get("source_url") or "")
        existing = self.find_by_source(source_url) if source_url else None
        created_at = now_iso()
        if existing:
            note_id_value = existing["id"]
            final_path = existing["filePath"] or ""
            draft_path = self.relative_draft(note_id_value)
            with self._connect() as connection:
                connection.execute(
                    """
                    UPDATE notes SET title=?, platform=?, uploader=?, duration=?,
                        duration_text=?, thumbnail=?, status='processing',
                        transcript_source=?, model=?, updated_at=?, error=NULL,
                        trash_path=NULL, deleted_at=NULL
                    WHERE id=?
                    """,
                    (
                        meta.get("title") or existing["title"],
                        meta.get("platform") or existing["platform"],
                        meta.get("uploader") or existing["uploader"],
                        meta.get("duration") or existing["duration"],
                        meta.get("duration_text") or existing["durationText"],
                        meta.get("thumbnail") or "",
                        meta.get("transcript_source") or existing["transcriptSource"],
                        meta.get("model") or existing["model"],
                        now_iso(),
                        note_id_value,
                    ),
                )
            row = self.raw(note_id_value)
            result = _row_to_public(row) if row else existing
            result["filePath"] = final_path or self.default_final_path(note_id_value, meta)
            result["draftPath"] = draft_path
            return result

        note_id_value = note_id()
        final_path = self.default_final_path(note_id_value, meta)
        draft_path = self.relative_draft(note_id_value)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO notes (
                    id,title,file_path,draft_path,source_url,platform,uploader,
                    duration,duration_text,thumbnail,ai_summary,status,
                    transcript_source,model,created_at,updated_at,file_size,error
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    note_id_value,
                    meta.get("title") or "未命名视频",
                    final_path,
                    draft_path,
                    source_url or None,
                    meta.get("platform") or "",
                    meta.get("uploader") or "",
                    int(meta.get("duration") or 0),
                    meta.get("duration_text") or "",
                    meta.get("thumbnail") or "",
                    "",
                    "processing",
                    meta.get("transcript_source") or "",
                    meta.get("model") or "",
                    created_at,
                    created_at,
                    0,
                    "",
                ),
            )
        record = self.get(note_id_value)
        if record is None:
            raise RuntimeError("创建笔记索引失败")
        record["draftPath"] = draft_path
        return record

    def relative_draft(self, note_id_value: str) -> str:
        return relative_path(self.root / ".drafts" / f"{note_id_value}.md")

    def default_final_path(self, note_id_value: str, meta: dict[str, Any]) -> str:
        date = datetime.now().strftime("%Y-%m-%d")
        slug = slugify(str(meta.get("title") or "视频笔记"))
        return relative_path(self.root / f"{date}-{slug}-{note_id_value[-6:]}.md")

    def update(self, note_id_value: str, **fields: Any) -> None:
        allowed = {
            "title",
            "file_path",
            "draft_path",
            "source_url",
            "platform",
            "uploader",
            "duration",
            "duration_text",
            "thumbnail",
            "ai_summary",
            "status",
            "transcript_source",
            "model",
            "updated_at",
            "file_size",
            "error",
            "trash_path",
            "deleted_at",
        }
        fields["updated_at"] = fields.get("updated_at") or now_iso()
        keys = [key for key in fields if key in allowed]
        if not keys:
            return
        values = [fields[key] for key in keys]
        values.append(note_id_value)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE notes SET {', '.join(f'{key}=?' for key in keys)} WHERE id=?",
                values,
            )

    def list_notes(
        self,
        *,
        query: str = "",
        status: str = "",
        platform: str = "",
        sort: str = "updated",
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        if status == "trashed":
            where = ["status = 'trashed'"]
        else:
            where = ["status <> 'trashed'"]
        params: list[Any] = []
        if query.strip():
            like = f"%{query.strip()}%"
            where.append("(title LIKE ? OR ai_summary LIKE ? OR source_url LIKE ? OR uploader LIKE ?)")
            params.extend([like, like, like, like])
        if status and status not in {"all", "trashed"}:
            where.append("status = ?")
            params.append(status)
        if platform:
            where.append("platform = ?")
            params.append(platform)
        order = "created_at DESC" if sort == "created" else "updated_at DESC"
        page = max(1, int(page or 1))
        page_size = max(1, min(200, int(page_size or 50)))
        offset = (page - 1) * page_size
        where_sql = " AND ".join(where)
        with self._connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) AS n FROM notes WHERE {where_sql}", params
            ).fetchone()["n"]
            rows = connection.execute(
                f"SELECT * FROM notes WHERE {where_sql} ORDER BY {order} LIMIT ? OFFSET ?",
                [*params, page_size, offset],
            ).fetchall()
        return {
            "items": [_row_to_public(row) for row in rows],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    def content_path(self, note_id_value: str) -> Path | None:
        row = self.raw(note_id_value)
        if row is None:
            return None
        if row["status"] in {"processing", "error"} and row["draft_path"]:
            draft = absolute_path(row["draft_path"])
            if draft and draft.is_file():
                return draft
        path = absolute_path(row["file_path"])
        if path and path.is_file():
            return path
        if row["draft_path"]:
            draft = absolute_path(row["draft_path"])
            if draft and draft.is_file():
                return draft
        return None

    def read_content(self, note_id_value: str) -> str:
        path = self.content_path(note_id_value)
        if path is None:
            raise FileNotFoundError("笔记文件不存在")
        return path.read_text(encoding="utf-8")

    def mark_trashed(self, ids: Iterable[str]) -> dict[str, Any]:
        deleted = 0
        failed: list[str] = []
        for note_id_value in list(dict.fromkeys(ids)):
            row = self.raw(note_id_value)
            if row is None:
                failed.append(note_id_value)
                continue
            moved: list[str] = []
            try:
                for key in ("file_path", "draft_path"):
                    path = absolute_path(row[key])
                    if path and path.is_file():
                        target = self.root / ".trash" / note_id_value / path.name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(path), str(target))
                        moved.append(relative_path(target))
                self.update(
                    note_id_value,
                    status="trashed",
                    trash_path=moved[0] if moved else "",
                    deleted_at=now_iso(),
                )
                deleted += 1
            except OSError:
                failed.append(note_id_value)
        return {"deleted": deleted, "failed": failed}

    def restore(self, ids: Iterable[str]) -> dict[str, Any]:
        restored = 0
        failed: list[str] = []
        for note_id_value in list(dict.fromkeys(ids)):
            row = self.raw(note_id_value)
            if row is None or not row["trash_path"]:
                failed.append(note_id_value)
                continue
            try:
                source = absolute_path(row["trash_path"])
                target = absolute_path(row["file_path"])
                if source and source.is_file() and target:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(source), str(target))
                self.update(
                    note_id_value,
                    status="done",
                    trash_path="",
                    deleted_at="",
                )
                restored += 1
            except OSError:
                failed.append(note_id_value)
        return {"restored": restored, "failed": failed}

    def purge_trash(self) -> int:
        cutoff = datetime.now().astimezone() - timedelta(days=LIBRARY_TRASH_TTL_DAYS)
        removed = 0
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM notes WHERE status='trashed'"
            ).fetchall()
        for row in rows:
            deleted_at = row["deleted_at"] or ""
            try:
                stamp = datetime.fromisoformat(deleted_at)
            except ValueError:
                stamp = None
            if stamp is not None and stamp > cutoff:
                continue
            trash = self.root / ".trash" / row["id"]
            shutil.rmtree(trash, ignore_errors=True)
            with self._connect() as connection:
                connection.execute("DELETE FROM notes WHERE id=?", (row["id"],))
            removed += 1
        return removed

    def build_zip(self, ids: Iterable[str]) -> Path:
        selected = list(dict.fromkeys(ids))
        if not selected:
            raise ValueError("请先选择要下载的笔记")
        target_dir = CACHE_DIR / "library-zips"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"clipdock-notes-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
        manifest = ["# ClipDock 笔记导出", ""]
        count = 0
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for note_id_value in selected:
                row = self.raw(note_id_value)
                path = self.content_path(note_id_value) if row else None
                if row is None or path is None:
                    continue
                name = Path(row["file_path"]).name or f"{note_id_value}.md"
                archive.write(path, arcname=f"notes/{name}")
                manifest.append(f"- [{row['title']}](notes/{name})")
                if row["source_url"]:
                    manifest.append(f"  出处：{row['source_url']}")
                manifest.append("")
                count += 1
        if count == 0:
            target.unlink(missing_ok=True)
            raise ValueError("选中的笔记没有可下载文件")
        manifest_path = target_dir / "manifest.tmp"
        manifest_path.write_text("\n".join(manifest), encoding="utf-8")
        with zipfile.ZipFile(target, "a", zipfile.ZIP_DEFLATED) as archive:
            archive.write(manifest_path, arcname="index.md")
        manifest_path.unlink(missing_ok=True)
        return target

    def rebuild_from_files(self) -> int:
        count = 0
        for path in sorted(self.root.glob("*.md")):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
                data, _body = parse_frontmatter(text)
            except OSError:
                continue
            if not data.get("id"):
                data["id"] = "note_" + uuid.uuid5(uuid.NAMESPACE_URL, str(path)).hex[:12]
            note_id_value = str(data["id"])
            source_url = str(data.get("source_url") or "")
            existing = self.find_by_source(source_url) if source_url else self.get(note_id_value)
            if existing:
                note_id_value = existing["id"]
            self.update(
                note_id_value,
                title=str(data.get("title") or path.stem),
                file_path=relative_path(path),
                draft_path="",
                source_url=source_url,
                platform=str(data.get("platform") or ""),
                uploader=str(data.get("uploader") or ""),
                duration=int(data.get("duration") or 0),
                duration_text=str(data.get("duration_text") or ""),
                thumbnail=str(data.get("thumbnail") or ""),
                ai_summary=str(data.get("ai_summary") or ""),
                status="done",
                transcript_source=str(data.get("transcript_source") or ""),
                model=str(data.get("model") or ""),
                file_size=path.stat().st_size,
                error="",
            )
            if not existing:
                # update() cannot insert; create a minimal row first.
                with self._connect() as connection:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO notes (
                          id,title,file_path,source_url,platform,uploader,duration,
                          duration_text,thumbnail,ai_summary,status,transcript_source,
                          model,created_at,updated_at,file_size,error
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            note_id_value,
                            str(data.get("title") or path.stem),
                            relative_path(path),
                            source_url or None,
                            str(data.get("platform") or ""),
                            str(data.get("uploader") or ""),
                            int(data.get("duration") or 0),
                            str(data.get("duration_text") or ""),
                            str(data.get("thumbnail") or ""),
                            str(data.get("ai_summary") or ""),
                            "done",
                            str(data.get("transcript_source") or ""),
                            str(data.get("model") or ""),
                            now_iso(),
                            now_iso(),
                            path.stat().st_size,
                            "",
                        ),
                    )
            count += 1
        return count


library_store = LibraryStore()
