import json
import time
from pathlib import Path

import backend.summary as summary_module
from backend.library import LibraryStore
from backend.summary import (
    SummaryJob,
    SummaryStore,
    _extract_json,
    _normalize_summary,
    parse_subtitle_file,
    summarize_transcript,
    write_article,
)


def test_parse_vtt_subtitle(tmp_path: Path):
    path = tmp_path / "sub.zh-Hans.vtt"
    path.write_text(
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:03.000\n"
        "你好，<b>这是</b>第一句。\n\n"
        "00:00:04.500 --> 00:00:06.000\n"
        "第二句。\n",
        encoding="utf-8",
    )
    result = parse_subtitle_file(path)
    assert "[00:01] 你好，这是第一句。" in result
    assert "[00:04] 第二句。" in result


def test_parse_bilibili_json_subtitle(tmp_path: Path):
    path = tmp_path / "sub.zh.json"
    path.write_text(
        json.dumps(
            {
                "body": [
                    {"from": 1.2, "to": 3.0, "content": "第一段"},
                    {"from": 4.0, "to": 6.0, "content": "第二段"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = parse_subtitle_file(path)
    assert "[00:01] 第一段" in result
    assert "[00:04] 第二段" in result


def test_extract_json_from_code_fence():
    data = _extract_json('```json\n{"tldr": "一句话", "keyPoints": ["a"]}\n```')
    assert data["tldr"] == "一句话"


def test_extract_json_ignores_trailing_text():
    data = _extract_json('好的：\n{"tldr": "一句话", "keyPoints": []}\n以上是总结。')
    assert data["tldr"] == "一句话"


def test_summarize_repairs_invalid_json(monkeypatch):
    calls = []

    def fake_chat(messages, max_tokens=2200):
        calls.append(messages[-1]["content"])
        if len(calls) == 1:
            return "这不是 JSON，只是一段解释。"
        return '{"tldr": "修复后的总结", "keyPoints": [], "chapters": []}'

    monkeypatch.setattr(summary_module, "_chat", fake_chat)
    result = summarize_transcript("[00:00] 测试内容", lambda value: None)
    assert result["tldr"] == "修复后的总结"
    assert len(calls) == 2


def test_normalize_summary_keeps_structure():
    result = _normalize_summary(
        {
            "tldr": "这是总结",
            "keyPoints": ["要点一", "要点二"],
            "chapters": [{"time": "01:20", "title": "开场", "summary": "内容"}],
            "quotes": ["原话"],
            "keywords": ["关键词"],
            "suitableFor": "适合所有人",
        }
    )
    assert result["tldr"] == "这是总结"
    assert result["chapters"][0]["time"] == "01:20"
    assert result["quotes"] == ["原话"]


def test_summarize_transcript_with_mock_llm(monkeypatch):
    monkeypatch.setattr(
        summary_module,
        "_chat",
        lambda messages, max_tokens=2200: json.dumps(
            {
                "tldr": "一句话总结",
                "keyPoints": ["要点一", "要点二"],
                "chapters": [{"time": "00:10", "title": "开场", "summary": "内容"}],
                "quotes": ["原话"],
                "keywords": ["测试"],
                "suitableFor": "测试用户",
            },
            ensure_ascii=False,
        ),
    )
    result = summarize_transcript("[00:10] 测试内容", lambda value: None)
    assert result["tldr"] == "一句话总结"
    assert result["chapters"][0]["time"] == "00:10"


def test_summary_store_pipeline_with_subtitles(monkeypatch, tmp_path):
    monkeypatch.setattr(summary_module, "SUMMARY_ENABLED", True)
    monkeypatch.setattr(summary_module, "SUMMARY_ARTICLE_ENABLED", False)
    monkeypatch.setattr(summary_module, "SUMMARY_DIR", tmp_path / "jobs")
    monkeypatch.setattr(summary_module, "SUMMARY_CACHE_DIR", tmp_path / "cache")
    (tmp_path / "jobs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "cache").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        summary_module,
        "fetch_subtitle_text",
        lambda url, directory, should_cancel=None: "[00:00] 这是字幕内容",
    )
    monkeypatch.setattr(
        summary_module,
        "summarize_transcript",
        lambda transcript, progress, should_cancel=None: {
            "tldr": "字幕总结",
            "keyPoints": ["一", "二", "三", "四"],
            "chapters": [{"time": "00:00", "title": "开场", "summary": "内容"}],
            "quotes": [],
            "keywords": ["测试"],
            "suitableFor": "测试",
            "generatedAt": 1,
        },
    )
    library = LibraryStore(tmp_path / "library.sqlite3", tmp_path / "library")
    store = SummaryStore(
        library=library, persist_path=tmp_path / "summary-jobs.json"
    )
    try:
        created = store.create(
            url="https://example.com/video",
            title="测试视频",
            thumbnail=None,
            platform="B站",
            duration=60,
        )
        deadline = time.time() + 5
        job = created
        while time.time() < deadline:
            job = store.get(created["id"])
            if job["status"] in {"done", "error"}:
                break
            time.sleep(0.03)
        assert job["status"] == "done"
        assert job["result"]["tldr"] == "字幕总结"
        assert len(job["result"]["chapters"]) == 1
        notes = library.list_notes()["items"]
        assert len(notes) == 1
        assert notes[0]["status"] == "done"
        assert "字幕总结" in notes[0]["aiSummary"]
        assert "这是字幕内容" in library.read_content(notes[0]["id"])
    finally:
        store.shutdown()


def test_write_article_with_mock_llm(monkeypatch):
    monkeypatch.setattr(summary_module, "SUMMARY_ARTICLE_ENABLED", True)
    monkeypatch.setattr(
        summary_module,
        "_chat",
        lambda messages, max_tokens=2200: "## 开场\n\n这是整理后的完整文案。",
    )
    article = write_article(
        "[00:00] 这是原始转写内容，比较碎。",
        {"tldr": "一句话", "chapters": [{"time": "00:00", "title": "开场"}]},
        "测试视频",
        lambda value: None,
    )
    assert article.startswith("# 测试视频")
    assert "## 开场" in article
    assert "AI 整理" in article


def test_summary_store_caches_transcript_and_article(monkeypatch, tmp_path):
    monkeypatch.setattr(summary_module, "SUMMARY_ENABLED", True)
    monkeypatch.setattr(summary_module, "SUMMARY_ARTICLE_ENABLED", True)
    monkeypatch.setattr(summary_module, "SUMMARY_DIR", tmp_path / "jobs")
    monkeypatch.setattr(summary_module, "SUMMARY_CACHE_DIR", tmp_path / "cache")
    (tmp_path / "jobs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "cache").mkdir(parents=True, exist_ok=True)

    calls = {"fetch": 0}

    def fake_fetch(url, directory, should_cancel=None):
        calls["fetch"] += 1
        return "[00:00] 这是字幕内容，足够长。"

    monkeypatch.setattr(summary_module, "fetch_subtitle_text", fake_fetch)
    monkeypatch.setattr(
        summary_module,
        "summarize_transcript",
        lambda transcript, progress, should_cancel=None: {
            "tldr": "字幕总结",
            "keyPoints": ["一", "二"],
            "chapters": [{"time": "00:00", "title": "开场", "summary": "内容"}],
            "quotes": [],
            "keywords": ["测试"],
            "suitableFor": "测试",
            "generatedAt": 1,
        },
    )
    monkeypatch.setattr(
        summary_module,
        "write_article",
        lambda transcript, summary, title, progress, should_cancel=None: "# 测试视频\n\n整理后的完整文案。",
    )

    library = LibraryStore(tmp_path / "library.sqlite3", tmp_path / "library")
    store = SummaryStore(
        library=library, persist_path=tmp_path / "summary-jobs.json"
    )
    try:
        created = store.create(
            url="https://example.com/cache-video",
            title="测试视频",
            thumbnail=None,
            platform="B站",
            duration=60,
        )
        deadline = time.time() + 5
        job = created
        while time.time() < deadline:
            job = store.get(created["id"])
            if job["status"] == "done" and job["articleStatus"] == "done":
                break
            time.sleep(0.03)
        assert job["status"] == "done"
        assert job["articleStatus"] == "done"
        assert job["transcriptAvailable"] is True
        assert "这是字幕内容" in store.transcript(created["id"])["transcript"]
        assert "整理后的完整文案" in store.article(created["id"])["article"]

        # 第二次请求同一 URL 应直接命中缓存，不再抓字幕。
        second = store.create(
            url="https://example.com/cache-video",
            title="测试视频",
            thumbnail=None,
            platform="B站",
            duration=60,
        )
        assert second["status"] == "done"
        assert second["articleStatus"] == "done"
        assert calls["fetch"] == 1
        notes = library.list_notes()["items"]
        assert len(notes) == 1
        content = library.read_content(notes[0]["id"])
        assert "整理后的完整文案" in content
        assert "这是字幕内容" in content
        assert notes[0]["sourceUrl"] == "https://example.com/cache-video"
    finally:
        store.shutdown()


def test_summary_job_returns_full_result():
    job = SummaryJob(id="s1", url="https://example.com", directory=Path("."))
    job.result = {
        "tldr": "一句话",
        "keyPoints": ["一", "二", "三", "四"],
        "chapters": [{"time": "00:00", "title": "开场", "summary": "内容"}],
        "quotes": ["原话"],
        "keywords": ["a"],
        "suitableFor": "适合所有人",
    }
    full = job.public()
    assert full["result"]["tldr"] == "一句话"
    assert len(full["result"]["keyPoints"]) == 4
    assert full["result"]["chapters"][0]["title"] == "开场"
