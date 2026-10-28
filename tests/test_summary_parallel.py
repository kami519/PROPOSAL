from __future__ import annotations

import threading
import time

import pytest

import backend.summary as summary_module
from backend.errors import AppError
from backend.library import LibraryStore
from backend.summary import SummaryStore


def _library(tmp_path):
    return LibraryStore(tmp_path / "library.sqlite3", tmp_path / "library")


def _store(monkeypatch, tmp_path, *, library=None):
    monkeypatch.setattr(summary_module, "SUMMARY_ENABLED", True)
    monkeypatch.setattr(summary_module, "SUMMARY_ARTICLE_ENABLED", False)
    monkeypatch.setattr(summary_module, "SUMMARY_DIR", tmp_path / "jobs")
    monkeypatch.setattr(summary_module, "SUMMARY_CACHE_DIR", tmp_path / "cache")
    (tmp_path / "jobs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "cache").mkdir(parents=True, exist_ok=True)
    return SummaryStore(
        library=library or _library(tmp_path),
        persist_path=tmp_path / "summary-jobs.json",
    )


def _wait(store: SummaryStore, job_id: str, statuses: set[str], timeout: float = 5.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = store.get(job_id)
        if last["status"] in statuses:
            return last
        time.sleep(0.03)
    pytest.fail(f"job did not reach {statuses}; last={last}")


def _summary(tldr: str = "测试总结"):
    return {
        "tldr": tldr,
        "keyPoints": ["一", "二"],
        "chapters": [{"time": "00:00", "title": "开场", "summary": "内容"}],
        "quotes": [],
        "keywords": ["测试"],
        "suitableFor": "测试",
        "generatedAt": 1,
    }


def test_parallel_summary_jobs_run_concurrently(monkeypatch, tmp_path):
    monkeypatch.setattr(summary_module, "SUMMARY_WORKERS", 3)
    active = 0
    peak = 0
    lock = threading.Lock()

    def fake_fetch(url, directory, should_cancel=None):
        time.sleep(0.05)
        return "[00:00] 这是字幕内容，足够长。"

    def fake_summarize(transcript, progress, should_cancel=None):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            time.sleep(0.2)
            return _summary()
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(summary_module, "fetch_subtitle_text", fake_fetch)
    monkeypatch.setattr(summary_module, "summarize_transcript", fake_summarize)
    store = _store(monkeypatch, tmp_path)
    try:
        created = [
            store.create(
                url=f"https://example.com/parallel-{index}",
                title=f"并行 {index}",
                thumbnail=None,
                platform="B站",
                duration=60,
            )
            for index in range(3)
        ]
        jobs = [_wait(store, item["id"], {"done", "error"}) for item in created]
        assert [job["status"] for job in jobs] == ["done", "done", "done"]
        assert peak >= 2
    finally:
        store.shutdown()


def test_same_url_is_deduped_while_active(monkeypatch, tmp_path):
    def fake_fetch(url, directory, should_cancel=None):
        time.sleep(0.3)
        return "[00:00] 这段内容足够长。"

    monkeypatch.setattr(summary_module, "SUMMARY_WORKERS", 1)
    monkeypatch.setattr(summary_module, "fetch_subtitle_text", fake_fetch)
    monkeypatch.setattr(
        summary_module,
        "summarize_transcript",
        lambda transcript, progress, should_cancel=None: _summary(),
    )
    store = _store(monkeypatch, tmp_path)
    try:
        first = store.create(
            url="https://example.com/dedupe",
            title="去重",
            thumbnail=None,
            platform="B站",
            duration=60,
        )
        second = store.create(
            url="https://example.com/dedupe",
            title="去重",
            thumbnail=None,
            platform="B站",
            duration=60,
        )
        assert second["id"] == first["id"]
        assert second["deduped"] is True
        store.cancel(first["id"])
        _wait(store, first["id"], {"cancelled"})
    finally:
        store.shutdown()


def test_cancel_queued_job_marks_note_cancelled(monkeypatch, tmp_path):
    def fake_fetch(url, directory, should_cancel=None):
        time.sleep(0.5)
        return "[00:00] 这段内容足够长。"

    monkeypatch.setattr(summary_module, "SUMMARY_WORKERS", 1)
    monkeypatch.setattr(summary_module, "fetch_subtitle_text", fake_fetch)
    monkeypatch.setattr(
        summary_module,
        "summarize_transcript",
        lambda transcript, progress, should_cancel=None: _summary(),
    )
    library = _library(tmp_path)
    store = _store(monkeypatch, tmp_path, library=library)
    try:
        first = store.create(
            url="https://example.com/first",
            title="第一个",
            thumbnail=None,
            platform="B站",
            duration=60,
        )
        _wait(store, first["id"], {"processing"})
        second = store.create(
            url="https://example.com/second",
            title="第二个",
            thumbnail=None,
            platform="B站",
            duration=60,
        )
        cancelled = store.cancel(second["id"])
        assert cancelled["status"] in {"cancelling", "cancelled"}
        cancelled = _wait(store, second["id"], {"cancelled"})
        assert cancelled["canRetry"] is True
        note = library.find_by_source("https://example.com/second")
        assert note is not None
        assert note["status"] == "cancelled"
        assert library.list_notes(status="cancelled")["total"] == 1
        store.cancel(first["id"])
        _wait(store, first["id"], {"cancelled"})
    finally:
        store.shutdown()


def test_retry_reuses_job_and_reaches_done(monkeypatch, tmp_path):
    attempts = {"count": 0}

    def fake_fetch(url, directory, should_cancel=None):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise AppError("FETCH_FAILED", "测试失败", 502)
        return "[00:00] 重试后的内容足够长。"

    monkeypatch.setattr(summary_module, "fetch_subtitle_text", fake_fetch)
    monkeypatch.setattr(
        summary_module,
        "summarize_transcript",
        lambda transcript, progress, should_cancel=None: _summary("重试成功"),
    )
    store = _store(monkeypatch, tmp_path)
    try:
        created = store.create(
            url="https://example.com/retry",
            title="重试",
            thumbnail=None,
            platform="B站",
            duration=60,
        )
        failed = _wait(store, created["id"], {"error"})
        assert failed["canRetry"] is True
        retried = store.retry(created["id"])
        assert retried["id"] == created["id"]
        done = _wait(store, created["id"], {"done", "error"})
        assert done["status"] == "done"
        assert done["retryCount"] == 1
        assert done["result"]["tldr"] == "重试成功"
    finally:
        store.shutdown()


def test_queue_limit_returns_friendly_error(monkeypatch, tmp_path):
    def fake_fetch(url, directory, should_cancel=None):
        time.sleep(0.4)
        return "[00:00] 这段内容足够长。"

    monkeypatch.setattr(summary_module, "SUMMARY_WORKERS", 1)
    monkeypatch.setattr(summary_module, "SUMMARY_QUEUE_MAX", 1)
    monkeypatch.setattr(summary_module, "fetch_subtitle_text", fake_fetch)
    store = _store(monkeypatch, tmp_path)
    try:
        first = store.create(
            url="https://example.com/busy-1",
            title="忙碌",
            thumbnail=None,
            platform="B站",
            duration=60,
        )
        with pytest.raises(AppError) as caught:
            store.create(
                url="https://example.com/busy-2",
                title="忙碌二",
                thumbnail=None,
                platform="B站",
                duration=60,
            )
        assert caught.value.code == "SUMMARY_TOO_BUSY"
        store.cancel(first["id"])
        _wait(store, first["id"], {"cancelled"})
    finally:
        store.shutdown()


def test_list_is_lightweight_and_filters(monkeypatch, tmp_path):
    monkeypatch.setattr(
        summary_module,
        "fetch_subtitle_text",
        lambda url, directory, should_cancel=None: "[00:00] 这段内容足够长。",
    )
    monkeypatch.setattr(
        summary_module,
        "summarize_transcript",
        lambda transcript, progress, should_cancel=None: _summary(),
    )
    store = _store(monkeypatch, tmp_path)
    try:
        created = store.create(
            url="https://example.com/list",
            title="列表",
            thumbnail=None,
            platform="B站",
            duration=60,
        )
        _wait(store, created["id"], {"done"})
        listing = store.list_jobs(ids=[created["id"]])
        assert listing["items"][0]["result"] is None
        assert listing["items"][0]["hasResult"] is True
        assert listing["items"][0]["tldr"] == "测试总结"
        assert listing["active"] == 0
        assert store.list_jobs(status="done")["items"]
    finally:
        store.shutdown()


def test_job_snapshot_survives_new_store(monkeypatch, tmp_path):
    monkeypatch.setattr(
        summary_module,
        "fetch_subtitle_text",
        lambda url, directory, should_cancel=None: "[00:00] 这段内容足够长。",
    )
    monkeypatch.setattr(
        summary_module,
        "summarize_transcript",
        lambda transcript, progress, should_cancel=None: _summary("快照总结"),
    )
    library = _library(tmp_path)
    store = _store(monkeypatch, tmp_path, library=library)
    created = store.create(
        url="https://example.com/snapshot",
        title="快照",
        thumbnail=None,
        platform="B站",
        duration=60,
    )
    _wait(store, created["id"], {"done"})
    store.shutdown()

    restored = SummaryStore(
        library=library, persist_path=tmp_path / "summary-jobs.json"
    )
    try:
        job = restored.get(created["id"])
        assert job["status"] == "done"
        assert job["result"]["tldr"] == "快照总结"
    finally:
        restored.shutdown()


def test_chat_retries_rate_limit(monkeypatch):
    calls = {"count": 0}

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.headers = {}
            self.text = "rate limited"

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return FakeResponse(429, {})
            return FakeResponse(
                200, {"choices": [{"message": {"content": "重试成功"}}]}
            )

    monkeypatch.setattr(summary_module, "SUMMARY_ENABLED", True)
    monkeypatch.setattr(summary_module, "SUMMARY_LLM_RETRIES", 2)
    monkeypatch.setattr(summary_module, "httpx", type("FakeHttpx", (), {
        "Client": FakeClient,
        "TimeoutException": type("TimeoutException", (Exception,), {}),
        "ConnectError": type("ConnectError", (Exception,), {}),
        "HTTPError": type("HTTPError", (Exception,), {}),
        "Response": FakeResponse,
    }))
    monkeypatch.setattr(summary_module.time, "sleep", lambda *_args: None)

    result = summary_module._chat([{"role": "user", "content": "test"}])
    assert result == "重试成功"
    assert calls["count"] == 2
