"""P2-B-5: bridge must validate Phase 1 CSV columns.

ROOT-CAUSE BEING VERIFIED:
  Every `row.get(...)` returned empty string silently when column was
  missing. Column rename in Phase 1 → all rows become empty strings →
  silent regression to "no safety data" state.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path("/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/phase1_bridge.py")


def test_bridge_has_validate_phase1_columns_helper():
    src = _FILE.read_text()
    assert "_validate_phase1_columns" in src, (
        "P2-B-5 REGRESSION: bridge does not define _validate_phase1_columns "
        "helper. Phase 1 CSV column renames will silently produce empty "
        "rows with no error signal."
    )


def test_bridge_has_expected_columns_dict():
    src = _FILE.read_text()
    # The fix defines a per-source expected-columns mapping.
    assert "_PHASE1_EXPECTED_COLUMNS" in src or "EXPECTED_COLUMNS" in src, (
        "P2-B-5 REGRESSION: bridge does not define expected-columns mapping."
    )


def test_bridge_calls_validate_in_read_phase1_outputs():
    src = _FILE.read_text()
    # _validate_phase1_columns must actually be CALLED, not just defined.
    call_count = src.count("_validate_phase1_columns(")
    # Subtract 1 for the def line
    assert call_count >= 2, (
        f"P2-B-5 REGRESSION: _validate_phase1_columns defined but only "
        f"called {call_count - 1} time(s). Must be called for every "
        f"Phase 1 source CSV read."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
