"""ML-5: ChemBERTa local_files_only logic must honor caller on first attempt.

v27 ROOT FIX verification: the buggy `and` pattern must be gone, the fixed
`or` pattern (or equivalent via temp variable) must be present.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path("/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/chemberta_encoder.py")


def test_chemberta_no_buggy_and_pattern_in_live_code():
    """Live code (not comments) must NOT use the buggy `and` pattern."""
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

    buggy = re.search(
        r"local_files_only\s*=\s*\(\s*local_files_only\s+and\s+attempt\s*>\s*0\s*\)",
        live_src,
    )
    assert not buggy, (
        "ML-5 REGRESSION: chemberta_encoder still uses "
        "`local_files_only=(local_files_only and attempt > 0)` in live "
        "code. This is False on attempt 0 → first attempt always contacts "
        "HF Hub even in regulatory_mode. Use `or` instead of `and`."
    )


def test_chemberta_uses_or_pattern():
    """The fix must use `or` (either directly or via a temp variable)."""
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

    # The fix may use a temp variable like `_attempt_local_only = local_files_only or attempt > 0`
    # or directly `local_files_only=(local_files_only or attempt > 0 ...)`
    fixed = re.search(
        r"local_files_only\s+or\s+attempt\s*>\s*0",
        live_src,
    )
    assert fixed, (
        "ML-5 REGRESSION: chemberta_encoder does not use "
        "`local_files_only or attempt > 0` pattern. The fix must honor "
        "the caller's request on first attempt."
    )


def test_chemberta_honors_hf_hub_offline():
    """The fix should also honor HF_HUB_OFFLINE=1 env var."""
    src = _FILE.read_text()
    assert "HF_HUB_OFFLINE" in src, (
        "ML-5 REGRESSION: chemberta_encoder does not check HF_HUB_OFFLINE "
        "env var. Air-gapped clusters cannot force offline mode."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
