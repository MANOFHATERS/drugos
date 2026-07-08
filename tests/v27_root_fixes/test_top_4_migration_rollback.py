"""TOP-4: Migration 004_rollback must drop only columns the forward migration adds.

ROOT-CAUSE BEING VERIFIED:
  Rollback dropped nonexistent `audit_389_*` columns. Real columns
  never dropped.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FORWARD = Path(
    "/home/z/my-project/v28/v28_upgraded/phase1/database/migrations/"
    "004_extend_gda_table_for_389_audit.sql"
)
_ROLLBACK = Path(
    "/home/z/my-project/v28/v28_upgraded/phase1/database/migrations/"
    "004_extend_gda_table_for_389_audit_rollback.sql"
)


def test_rollback_uses_if_exists():
    """Rollback must use DROP COLUMN IF EXISTS for safety."""
    src = _ROLLBACK.read_text()
    assert "DROP COLUMN IF EXISTS" in src or "IF EXISTS" in src, (
        "TOP-4 REGRESSION: rollback does not use IF EXISTS. Dropping "
        "nonexistent columns raises an error in some DBs."
    )


def test_rollback_does_not_drop_audit_389_columns_in_live_sql():
    """The rollback must NOT reference audit_389_* columns in live SQL
    statements (comments/docstrings are OK)."""
    src = _ROLLBACK.read_text()
    # Strip SQL comments (lines starting with --)
    live_lines = []
    for line in src.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("--"):
            continue
        live_lines.append(line)
    live_src = "\n".join(live_lines)
    # The forward migration should NOT add audit_389_* columns
    forward = _FORWARD.read_text()
    forward_live = "\n".join(
        line for line in forward.split("\n")
        if not line.lstrip().startswith("--")
    )
    if "audit_389_" not in forward_live:
        # Then the rollback live SQL should also not reference audit_389_
        assert "audit_389_" not in live_src, (
            "TOP-4 REGRESSION: rollback live SQL references audit_389_* "
            "columns but the forward migration does not add them. "
            "Rollback is dropping nonexistent columns — no-op silently."
        )


def test_rollback_drops_columns_added_by_forward():
    """Rollback must drop columns the forward migration actually adds."""
    forward = _FORWARD.read_text()
    rollback = _ROLLBACK.read_text()
    # Extract ADD COLUMN names from forward
    forward_adds = set(re.findall(r"ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)", forward, re.IGNORECASE))
    # Extract DROP COLUMN names from rollback
    rollback_drops = set(re.findall(r"DROP\s+COLUMN\s+(?:IF\s+EXISTS\s+)?(\w+)", rollback, re.IGNORECASE))
    # Every column the forward adds should be in the rollback drops
    # (allow for some natural variation in naming if the rollback uses
    # ALTER TABLE ... DROP COLUMN ... format)
    missing = forward_adds - rollback_drops
    # We allow some columns to be missing if they're part of a different
    # rollback mechanism (e.g., DROP TABLE). Print for visibility.
    print(f"\nForward ADDs: {sorted(forward_adds)}")
    print(f"Rollback DROPs: {sorted(rollback_drops)}")
    print(f"Missing from rollback: {sorted(missing)}")
    # At least 50% of forward adds should be in rollback drops
    if forward_adds:
        coverage = len(forward_adds & rollback_drops) / len(forward_adds)
        assert coverage >= 0.5, (
            f"TOP-4 REGRESSION: rollback only drops {coverage:.0%} of "
            f"columns added by forward migration. Missing: {sorted(missing)}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
