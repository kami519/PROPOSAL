from fastapi.testclient import TestClient

import backend.app as app_module
import backend.summary as summary_module
from backend.library import LibraryStore
from backend.note_writer import NoteWriter

SAMPLE = {
    "title": "测试视频",
    "uploader": "测试作者",
    "duration": 60,
    "durationText": "1:00",
    "thumbnail": "https://example.com/cover.jpg",
    "webpageUrl": "https://example.com/video",
    "platform": "B站",
    "sourceHeight": 1080,
    "formats": [
        {
            "id": "720p",
            "label": "720P",
            "sublabel": "MP4",
            "height": 720,
            "ext": "mp4",
            "size": 1000,
            "sizeText": "1 KB",
            "kind": "video",
        },
        {
            "id": "1080p",
            "label": "1080P",
            "sublabel": "高清 · MP4",
            "height": 1080,
            "ext": "mp4",
            "size": 2000,
            "sizeText": "2 KB",
            "kind": "video",
        },
    ],
    "qualityNotice": {
        "code": "HIGHER_QUALITY_REQUIRES_LOGIN",
        "message": "源站还有 4K 超高清清晰度，但需要登录或会员权限。",
        "missingFormats": ["4K 超高清"],
        "maxAvailableHeight": 1080,
    },
}


def _client() -> TestClient:
    return TestClient(app_module.app)


def test_health():
    response = _client().get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["ytDlpVersion"]


def test_analyze_with_mocked_downloader(monkeypatch):
    monkeypatch.setattr(app_module, "analyze_url", lambda url: SAMPLE)
    response = _client().post("/api/analyze", json={"url": "https://example.com/video"})
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "测试视频"
    assert len(data["formats"]) == 2
    assert data["qualityNotice"]["missingFormats"] == ["4K 超高清"]


def test_analyze_rejects_invalid_url():
    response = _client().post("/api/analyze", json={"url": "file:///etc/passwd"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_URL"


def test_summary_requires_configuration(monkeypatch):
    # .env may contain a real key on the developer machine; this test is about
    # the unconfigured path, so force the module flag off.
    monkeypatch.setattr(summary_module, "SUMMARY_ENABLED", False)
    response = _client().post(
        "/api/summaries",
        json={
            "url": "https://example.com/video",
            "title": "测试",
            "duration": 60,
        },
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SUMMARY_NOT_CONFIGURED"


def test_summary_article_routes(monkeypatch):
    monkeypatch.setattr(
        summary_module.summary_store,
        "transcript",
        lambda job_id: {"id": job_id, "source": "subtitle", "chars": 4, "transcript": "测试"},
    )
    monkeypatch.setattr(
        summary_module.summary_store,
        "article",
        lambda job_id: {"id": job_id, "status": "done", "article": "# 标题", "chars": 4, "error": None},
    )
    monkeypatch.setattr(
        summary_module.summary_store,
        "request_article",
        lambda job_id: {"id": job_id, "status": "done", "articleStatus": "processing"},
    )

    client = _client()
    transcript = client.get("/api/summaries/s1/transcript").json()
    assert transcript["transcript"] == "测试"
    article = client.get("/api/summaries/s1/article").json()
    assert article["article"] == "# 标题"
    started = client.post("/api/summaries/s1/article").json()
    assert started["articleStatus"] == "processing"


def test_library_endpoints(monkeypatch, tmp_path):
    library = LibraryStore(tmp_path / "library.sqlite3", tmp_path / "library")
    monkeypatch.setattr(app_module, "library_store", library)
    note = library.prepare_note(
        {
            "title": "测试笔记",
            "source_url": "https://example.com/video",
            "platform": "B站",
            "uploader": "测试UP",
            "duration": 60,
            "duration_text": "1:00",
        }
    )
    writer = NoteWriter(library, note)
    writer.start()
    writer.append_transcript("[00:00] 测试转写")
    writer.set_summary({"tldr": "测试摘要", "keyPoints": ["要点"]})
    writer.set_article("# 测试笔记\n\n整理后的正文。")
    writer.finalize()

    client = _client()
    listing = client.get("/api/library").json()
    assert listing["total"] == 1
    note_id = listing["items"][0]["id"]

    content = client.get(f"/api/library/{note_id}/content")
    assert content.status_code == 200
    assert "测试摘要" in content.text
    assert "整理后的正文" in content.text

    download = client.get(f"/api/library/{note_id}/download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/markdown")

    archive = client.post("/api/library/batch-download", json={"ids": [note_id]})
    assert archive.status_code == 200
    assert archive.headers["content-type"] == "application/zip"
    assert len(archive.content) > 100

    deleted = client.post("/api/library/batch-delete", json={"ids": [note_id]}).json()
    assert deleted["deleted"] == 1
    assert client.get("/api/library").json()["total"] == 0
    restored = client.post("/api/library/batch-restore", json={"ids": [note_id]}).json()
    assert restored["restored"] == 1
    assert client.get("/api/library").json()["total"] == 1


def test_job_allows_1080p_without_paywall(monkeypatch):
    def fake_create(**kwargs):
        return {"id": "test-job", "status": "queued", "format": kwargs["tier"]}

    monkeypatch.setattr(app_module.job_store, "create", fake_create)
    monkeypatch.setattr(app_module, "analyze_url", lambda url: SAMPLE)

    response = _client().post(
        "/api/jobs",
        json={"url": "https://example.com/video", "format": "1080p"},
    )
    assert response.status_code == 200
    assert response.json()["format"] == "1080p"


def test_job_rejects_unknown_format():
    response = _client().post(
        "/api/jobs",
        json={"url": "https://example.com/video", "format": "8k"},
    )
    assert response.status_code == 422


def test_job_control_endpoints(monkeypatch):
    calls = []

    def fake_action(name):
        def action(job_id):
            calls.append((name, job_id))
            return {"id": job_id, "status": name}

        return action

    monkeypatch.setattr(app_module.job_store, "pause", fake_action("paused"))
    monkeypatch.setattr(app_module.job_store, "resume", fake_action("queued"))
    monkeypatch.setattr(app_module.job_store, "cancel", fake_action("cancelled"))

    client = _client()
    assert client.post("/api/jobs/j1/pause").json()["status"] == "paused"
    assert client.post("/api/jobs/j1/resume").json()["status"] == "queued"
    assert client.post("/api/jobs/j1/cancel").json()["status"] == "cancelled"
    assert calls == [("paused", "j1"), ("queued", "j1"), ("cancelled", "j1")]
