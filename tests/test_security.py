import pytest

from backend.errors import AppError
from backend.security import normalize_url


@pytest.mark.parametrize(
    "raw",
    [
        "https://www.bilibili.com/video/BV1GJ411x7h7",
        "bilibili.com/video/BV1GJ411x7h7",
        "http://example.com/a.mp4",
    ],
)
def test_normalize_url_accepts_public_http(raw):
    result = normalize_url(raw)
    assert result.startswith(("http://", "https://"))


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "http://localhost:8000/secret",
        "http://127.0.0.1/secret",
        "http://192.168.1.10/secret",
        "http://[::1]/secret",
        "http://user:pass@example.com/video",
    ],
)
def test_normalize_url_rejects_unsafe_input(raw):
    with pytest.raises(AppError):
        normalize_url(raw)
