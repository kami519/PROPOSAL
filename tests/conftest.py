"""Workspace-local pytest temp fixtures.

The DSH sandbox on this machine cannot read directories created by
``tempfile.mkdtemp`` (Windows gives them a restrictive DACL). Pytest's
``tmp_path`` fixture uses that path, so we provide a small replacement that
creates directories with normal inherited permissions.
"""

from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

import pytest

_TMP = Path(__file__).resolve().parent.parent / ".tmp" / "pytest"
_TMP.mkdir(parents=True, exist_ok=True)


@pytest.fixture
def tmp_path(request) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", request.node.nodeid)[:80].strip("-")
    path = _TMP / "cases" / f"{safe}-{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
