"""P1-ER-9: protein_resolver duplicate count log must show actual count.

ROOT-CAUSE: `len(dup_result)` returned 1 (dict has 1 field) instead of
the actual duplicate count.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase1/entity_resolution/protein_resolver.py"
)


def test_duplicate_count_log_uses_actual_count():
    src = _FILE.read_text()
    # Find the duplicate count log line
    # The fix changed `len(dup_result)` to `len(dup_result.get("uniprot_id", []))`
    # or `sum(len(v) for v in dup_result.values())`.
    # The bug was `len(dup_result)` (always 1).
    # Look for the warning log call near find_duplicate_ids.
    m = re.search(
        r"find_duplicate_ids\s*\([^)]*\).*?logger\.warning\([^)]*len\([^)]+\)[^)]*\)",
        src,
        re.DOTALL,
    )
    if m:
        log_call = m.group(0)
        # Must NOT use bare `len(dup_result)`
        assert "len(dup_result)" not in log_call, (
            "P1-ER-9 REGRESSION: duplicate count log still uses "
            "`len(dup_result)` which always returns 1 (dict field count). "
            "Use `len(dup_result.get('uniprot_id', []))` instead."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
