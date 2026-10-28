import time
from pathlib import Path

import pytest

import backend.jobs as jobs_module
from backend.errors import AppError
from backend.jobs import JobStore


def _wait_for(client, job_id, statuses, timeout=5.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = client.get(job_id)
        if last["status"] in statuses:
            return last
        time.sleep(0.03)
    pytest.fail(f"job did not reach {statuses}; last={last}")


def _fake_download(seconds=2.0):
    def fake(url, tier, directory, *, progress, checkpoint=None):
        directory = Path(directory)
        for index in range(200):
            if checkpoint:
                checkpoint()
            progress(status="downloading", progress=min(95.0, index / 2), speed="1 MB/s", eta="00:01")
            time.sleep(seconds / 200)
        output = directory / "clip.mp4"
        output.write_bytes(b"fake-video")
        return output, output.name

    return fake


@pytest.fixture()
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs_module, "download_url", _fake_download())
    monkeypatch.setattr(jobs_module, "JOBS_DIR", tmp_path)
    instance = JobStore()
    yield instance
    instance.shutdown()


def test_pause_and_resume_keeps_job_directory(store):
    created = store.create(url="https://example.com/v", tier="720p", title="demo")
    job_id = created["id"]
    _wait_for(store, job_id, {"downloading"})
    paused = store.pause(job_id)
    assert paused["status"] in {"pausing", "paused"}
    paused = _wait_for(store, job_id, {"paused"})
    assert paused["canResume"] is True
    assert paused["canPause"] is False
    assert (jobs_module.JOBS_DIR / job_id).exists()

    resumed = store.resume(job_id)
    assert resumed["status"] in {"queued", "downloading"}
    done = _wait_for(store, job_id, {"done", "error"}, timeout=8.0)
    assert done["status"] == "done"
    assert done["downloadUrl"]


def test_cancel_removes_temporary_directory(store):
    created = store.create(url="https://example.com/v", tier="720p", title="demo")
    job_id = created["id"]
    _wait_for(store, job_id, {"downloading"})
    cancelled = store.cancel(job_id)
    assert cancelled["status"] in {"cancelling", "cancelled"}
    cancelled = _wait_for(store, job_id, {"cancelled"})
    assert cancelled["status"] == "cancelled"
    assert not (jobs_module.JOBS_DIR / job_id).exists()
    assert cancelled["canCancel"] is False


def test_download_concurrency_limit_queue(store, monkeypatch):
    monkeypatch.setattr(jobs_module, "DOWNLOAD_CONCURRENCY", 1)
    first = store.create(url="https://example.com/a", tier="720p", title="a")
    _wait_for(store, first["id"], {"downloading"})
    with pytest.raises(AppError) as caught:
        store.create(url="https://example.com/b", tier="720p", title="b")
    assert caught.value.code == "TOO_BUSY"
    store.cancel(first["id"])
    _wait_for(store, first["id"], {"cancelled"})
