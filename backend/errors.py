from __future__ import annotations


class AppError(Exception):
    """An expected, user-facing error with a stable machine code."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class SummaryCancelled(Exception):
    """Raised at a cooperative checkpoint when a summary job is cancelled."""


class DownloadInterrupted(Exception):
    """Base class for cooperative pause/cancel of a running download."""


class DownloadPaused(DownloadInterrupted):
    pass


class DownloadCancelled(DownloadInterrupted):
    pass
