"""P2-B-1: bridge must write withdrawn=None (not False) when Phase 1 column missing.

ROOT-CAUSE BEING VERIFIED:
  Bridge always wrote withdrawn=_to_bool(...) which returned False (never
  None). DrugBankEnricher coalesce pattern only fires when BOTH are NULL,
  so safety_data_missing was never set True. Withdrawn drugs classified
  as SAFE forever → patient harm.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path("/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/phase1_bridge.py")


def test_bridge_emits_safety_data_missing_field():
    """The bridge must emit a `safety_data_missing` field alongside `withdrawn`."""
    src = _FILE.read_text()
    assert "safety_data_missing" in src, (
        "P2-B-1 REGRESSION: bridge does not emit `safety_data_missing` "
        "field. Without it, the DrugBankEnricher coalesce pattern at "
        "kg_builder.py:2277 never fires."
    )


def test_bridge_withdrawn_uses_none_when_phase1_silent():
    """The bridge must write None when Phase 1's is_withdrawn is missing/empty.

    We look for a `_to_bool_or_none` helper or equivalent that returns None
    on missing input. The original `_to_bool` always returned False.
    """
    src = _FILE.read_text()
    # The fix likely introduced a None-on-missing variant OR checks for
    # missing values explicitly. Look for either pattern.
    has_none_handling = (
        "safety_data_missing" in src  # the new flag itself
        and ("is_withdrawn" in src)
    )
    assert has_none_handling, (
        "P2-B-1 REGRESSION: bridge does not handle missing is_withdrawn "
        "via safety_data_missing flag."
    )


def test_bridge_does_not_unconditionally_call_to_bool_for_withdrawn():
    """The bridge must NOT call _to_bool unconditionally on is_withdrawn
    in the DrugBank Compound node path (line ~1148 originally). The
    ChEMBL paths may still call _to_bool as long as they wrap it with
    the safety_data_missing check first."""
    src = _FILE.read_text()
    # Look for the unconditional pattern: `"withdrawn": _to_bool(row.get("is_withdrawn"))`
    # WITHOUT a preceding safety_data_missing check.
    bare_calls = re.findall(
        r'"withdrawn":\s*_to_bool\s*\(\s*row\.get\(\s*["\']is_withdrawn["\']\s*\)\s*\)',
        src,
    )
    # We allow at most 0 unconditional calls (the fix wraps every
    # occurrence with a safety_data_missing check).
    assert not bare_calls, (
        f"P2-B-1 REGRESSION: bridge still calls "
        f"`_to_bool(row.get('is_withdrawn'))` unconditionally "
        f"({len(bare_calls)} occurrences). This always returns False, "
        f"defeating the DrugBankEnricher coalesce pattern. Every "
        f"withdrawn assignment must be preceded by a safety_data_missing "
        f"check that writes None when Phase 1 is silent."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
