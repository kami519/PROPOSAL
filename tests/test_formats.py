from backend.formats import build_formats, label_for_height, selector_for


def _info(*heights: int) -> dict:
    formats = []
    for height in heights:
        formats.append(
            {
                "format_id": f"v{height}",
                "height": height,
                "width": int(height * 16 / 9),
                "vcodec": "avc1.640028",
                "acodec": "none",
                "ext": "mp4",
                "tbr": height * 2,
                "filesize": height * 1000,
            }
        )
    formats.append(
        {
            "format_id": "a1",
            "vcodec": "none",
            "acodec": "mp4a.40.2",
            "ext": "m4a",
            "abr": 128,
            "filesize": 2_000_000,
        }
    )
    return {"formats": formats, "duration": 60, "title": "demo"}


def test_1080p_adds_hd_tier_without_paywall():
    formats, max_height = build_formats(_info(360, 720, 1080))
    assert max_height == 1080
    by_id = {item["id"]: item for item in formats}
    assert by_id["720p"]["sublabel"] == "MP4"
    assert by_id["1080p"]["sublabel"] == "高清 · MP4"
    assert "pro" not in by_id["1080p"]
    assert "best" not in by_id


def test_4k_adds_best_tier():
    formats, max_height = build_formats(_info(720, 1080, 2160))
    assert max_height == 2160
    by_id = {item["id"]: item for item in formats}
    assert by_id["best"]["label"] == "4K"
    assert "pro" not in by_id["best"]


def test_low_quality_tier():
    formats, max_height = build_formats(_info(360, 480))
    assert max_height == 480
    by_id = {item["id"]: item for item in formats}
    assert by_id["720p"]["label"] == "480P"
    assert "1080p" not in by_id


def test_size_includes_audio_for_video_only():
    formats, _ = build_formats(_info(720))
    video = next(item for item in formats if item["id"] == "720p")
    assert video["size"] == 720 * 1000 + 2_000_000


def test_selectors_are_capped():
    assert "height<=720" in selector_for("720p")
    assert "height<=1080" in selector_for("1080p")
    assert selector_for("best") == "bestvideo+bestaudio/best"
    assert selector_for("audio") == "bestaudio/best"


def test_labels():
    assert label_for_height(2160) == "4K"
    assert label_for_height(1440) == "2K"
    assert label_for_height(1080) == "1080P"
    assert label_for_height(720) == "720P"
    assert label_for_height(None) == "原画质"
