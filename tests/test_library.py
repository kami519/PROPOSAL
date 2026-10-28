import json
import zipfile
from pathlib import Path

from backend.library import LibraryStore, parse_frontmatter
from backend.note_writer import NoteWriter


def _make_note(tmp_path: Path):
    library = LibraryStore(tmp_path / "library.sqlite3", tmp_path / "library")
    note = library.prepare_note(
        {
            "title": "从零开始认识显卡",
            "source_url": "https://example.com/video/1",
            "platform": "B站",
            "uploader": "硬件茶谈",
            "duration": 919,
            "duration_text": "15:19",
            "model": "deepseek-flash",
        }
    )
    writer = NoteWriter(library, note)
    writer.start()
    writer.append_transcript("[00:02] 显卡由散热模组和 GPU 核心组成。")
    writer.set_transcript_source("subtitle")
    writer.set_summary(
        {
            "tldr": "显卡科普",
            "keyPoints": ["显卡由多个模块组成"],
            "chapters": [{"time": "00:02", "title": "开场", "summary": "介绍显卡"}],
            "quotes": ["GPU 是核心"],
            "keywords": ["显卡", "GPU"],
        }
    )
    writer.set_article("# 显卡\n\n## 开场\n\n显卡由多个模块组成。")
    path = writer.finalize()
    return library, writer, path


def test_note_writer_final_markdown(tmp_path: Path):
    library, _writer, path = _make_note(tmp_path)
    text = path.read_text(encoding="utf-8")
    data, body = parse_frontmatter(text)
    assert data["title"] == "从零开始认识显卡"
    assert data["source_url"] == "https://example.com/video/1"
    assert data["ai_summary"] == "显卡科普"
    assert data["status"] == "done"
    assert "## AI 摘要" in body
    assert "## 完整文案" in body
    assert "[00:02] 显卡由散热模组" in body
    notes = library.list_notes()["items"]
    assert len(notes) == 1
    assert notes[0]["status"] == "done"
    assert notes[0]["fileName"].endswith(".md")


def test_library_batch_zip_and_trash_restore(tmp_path: Path):
    library, _writer, path = _make_note(tmp_path)
    notes = library.list_notes()["items"]
    note_id = notes[0]["id"]
    archive = library.build_zip([note_id])
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
    assert f"notes/{path.name}" in names
    assert "index.md" in names

    deleted = library.mark_trashed([note_id])
    assert deleted["deleted"] == 1
    assert not path.exists()
    assert library.list_notes()["total"] == 0
    assert library.list_notes(status="trashed")["total"] == 1

    restored = library.restore([note_id])
    assert restored["restored"] == 1
    assert path.exists()
    assert library.list_notes()["total"] == 1


def test_library_rebuilds_index_from_markdown(tmp_path: Path):
    library, _writer, path = _make_note(tmp_path)
    source = path.read_text(encoding="utf-8")
    assert "ai_summary" in source

    # Delete the index, keep the Markdown; a fresh store should rescan it.
    (tmp_path / "library.sqlite3").unlink()
    rebuilt = LibraryStore(tmp_path / "library.sqlite3", tmp_path / "library")
    notes = rebuilt.list_notes()["items"]
    assert len(notes) == 1
    assert notes[0]["title"] == "从零开始认识显卡"
    assert notes[0]["aiSummary"] == "显卡科普"
