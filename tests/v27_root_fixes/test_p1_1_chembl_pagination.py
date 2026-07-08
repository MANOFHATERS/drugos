"""P1-1: ChEMBL pagination must NOT silently truncate to 1 page when the
ChEMBL API omits ``total_count``.

v27 ROOT FIX verification: the buggy default-zero pattern must be GONE
from live code (it's OK for it to appear in comments explaining the fix).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path("/home/z/my-project/v28/v28_upgraded/phase1/pipelines/chembl_pipeline.py")


def test_chembl_pagination_no_total_count_default_zero_in_live_code():
    """The buggy `total_count = int(page_meta.get("total_count", 0))`
    pattern must NOT appear in live code (only in comments)."""
    src = _FILE.read_text()
    # Strip comments (lines starting with #, possibly with leading whitespace)
    live_lines = []
    for line in src.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # Also strip inline comments
        if "#" in line:
            line = line[: line.index("#")]
        live_lines.append(line)
    live_src = "\n".join(live_lines)

    # The buggy pattern: total_count = int(page_meta.get("total_count", 0))
    buggy = re.search(
        r"total_count\s*=\s*int\s*\(\s*page_meta\.get\s*\(\s*[\"']total_count[\"']\s*,\s*0\s*\)\s*\)",
        live_src,
    )
    assert not buggy, (
        "P1-1 REGRESSION: chembl_pipeline.py still has the buggy "
        "`total_count = int(page_meta.get('total_count', 0))` pattern in "
        "live code (not just comments). This silently truncates to page 1 "
        "when the API omits total_count."
    )


def test_chembl_pagination_short_page_termination():
    """The fix must use short-page termination (len(molecules) < PAGE_SIZE)."""
    src = _FILE.read_text()
    # Strip comments
    live_lines = []
    for line in src.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if "#" in line:
            line = line[: line.index("#")]
        live_lines.append(line)
    live_src = "\n".join(live_lines)

    # Look for short-page termination: len(molecules) < SOMETHING or
    # len(molecules) < PAGE_SIZE
    short_page = re.search(
        r"len\s*\(\s*molecules\s*\)\s*<\s*\w+",
        live_src,
    )
    assert short_page, (
        "P1-1 REGRESSION: chembl_pipeline.py pagination loop has no "
        "short-page termination fallback. Without it, missing total_count "
        "causes either infinite pagination or silent truncation."
    )


def test_chembl_pagination_post_loop_assertion_present():
    """Post-loop assertion must raise PipelineError on truncation."""
    src = _FILE.read_text()
    # The v27 ROOT FIX must raise on truncation (not just warn).
    assert src.count("raise PipelineError") >= 2, (
        "P1-1 REGRESSION: Expected at least 2 `raise PipelineError` "
        "statements (one in _download_molecules, one in _download_activities) "
        "for the post-loop completeness assertion."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
