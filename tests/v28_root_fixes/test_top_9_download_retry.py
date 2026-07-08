"""TOP-9: download_with_retry must use requests with resume, not urllib.urlretrieve.

ROOT-CAUSE: urllib.urlretrieve has no resume, no auth, no Content-Length.
Multi-GB downloads fail mid-stream and can't recover.

NOTE: The fix may reference `urlretrieve` in COMMENTS explaining what
was removed. That's fine. We only check LIVE code.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/config.py"
)


def _strip_comments_and_docstrings(src: str) -> str:
    """Strip Python comments and docstrings from source."""
    live_lines = []
    in_docstring = False
    for line in src.split("\n"):
        stripped = line.lstrip()
        # Track triple-quoted docstrings
        if '"""' in line:
            count = line.count('"""')
            if count == 1:
                in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        if stripped.startswith("#"):
            continue
        if "#" in line:
            line = line[: line.index("#")]
        live_lines.append(line)
    return "\n".join(live_lines)


def test_download_with_retry_does_not_use_urlretrieve_in_live_code():
    src = _FILE.read_text()
    # Find the download_with_retry function
    m = re.search(
        r"def\s+download_with_retry\b[^:]*:(.*?)(?=\ndef\s|\Z)",
        src,
        re.DOTALL,
    )
    assert m, "TOP-9 setup: cannot find download_with_retry"
    body = m.group(1)
    live_body = _strip_comments_and_docstrings(body)
    # Must NOT use urllib.urlretrieve in live code
    assert "urlretrieve" not in live_body, (
        "TOP-9 REGRESSION: download_with_retry still uses urllib.urlretrieve "
        "in live code. No resume, no auth, no Content-Length support."
    )


def test_download_with_retry_uses_requests_with_stream():
    src = _FILE.read_text()
    m = re.search(
        r"def\s+download_with_retry\b[^:]*:(.*?)(?=\ndef\s|\Z)",
        src,
        re.DOTALL,
    )
    body = m.group(1)
    live_body = _strip_comments_and_docstrings(body)
    assert "requests" in live_body, (
        "TOP-9 REGRESSION: download_with_retry does not use requests library."
    )
    assert "stream" in live_body, (
        "TOP-9 REGRESSION: download_with_retry does not use stream=True "
        "for memory-efficient downloads."
    )


def test_download_with_retry_supports_range_header():
    src = _FILE.read_text()
    m = re.search(
        r"def\s+download_with_retry\b[^:]*:(.*?)(?=\ndef\s|\Z)",
        src,
        re.DOTALL,
    )
    body = m.group(1)
    live_body = _strip_comments_and_docstrings(body)
    assert "Range" in live_body or "range" in live_body, (
        "TOP-9 REGRESSION: download_with_retry does not support Range "
        "header for resume. Multi-GB downloads can't recover from "
        "mid-stream failures."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
