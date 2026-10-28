from backend.downloader import YdlLogger, _quality_notice


BILIBILI_MESSAGE = (
    "[BiliBili] Format(s) HDR 真彩, 4K 超高清, 1080P 60帧 are missing; "
    "you have to become a premium member to download them. "
    "Use --cookies-from-browser or --cookies for the authentication."
)


def _adapter(message: str) -> YdlLogger:
    adapter = YdlLogger()
    adapter.debug(message)
    return adapter


def test_quality_notice_parses_missing_bilibili_formats():
    notice = _quality_notice(_adapter(BILIBILI_MESSAGE), 1080, cookies_configured=False)
    assert notice is not None
    assert notice["code"] == "HIGHER_QUALITY_REQUIRES_LOGIN"
    assert notice["missingFormats"] == ["HDR 真彩", "4K 超高清", "1080P 60帧"]
    assert "登录或会员权限" in notice["message"]
    assert "1080P" in notice["message"]


def test_quality_notice_mentions_existing_login_without_permission():
    notice = _quality_notice(_adapter(BILIBILI_MESSAGE), 1080, cookies_configured=True)
    assert notice is not None
    assert "当前登录信息没有对应权限" in notice["message"]


def test_quality_notice_none_when_no_missing_formats():
    assert _quality_notice(_adapter("Downloading video formats for cid 123"), 1080, cookies_configured=False) is None


def test_quality_notice_ignores_bitrate_only_missing_variant():
    message = (
        "Format(s) 1080P 高码率 are missing; you have to become a premium member "
        "to download them."
    )
    assert _quality_notice(_adapter(message), 1080, cookies_configured=False) is None


def test_quality_notice_ignores_unrelated_warning():
    adapter = YdlLogger()
    adapter.warning("Format(s) 4K are missing; premium member")
    assert _quality_notice(adapter, 1080, cookies_configured=False) is None
