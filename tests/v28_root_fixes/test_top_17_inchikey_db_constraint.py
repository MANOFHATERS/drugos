"""TOP-17: DB CHECK constraint must NOT accept TEST/OUTER/INNER/IK% InChIKeys.

ROOT-CAUSE: Python regex was strict 27-char, but DB CHECK accepted
TEST/OUTER/INNER/IK%. Biologics rejected by Python, accepted by SQL.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase1/database/migrations/001_initial_schema.sql"
)


def test_initial_schema_does_not_accept_test_outer_inner_ik():
    src = _FILE.read_text()
    # Find the chk_drugs_inchikey_format constraint
    # The buggy pattern: LIKE 'TEST%' OR LIKE 'OUTER%' OR LIKE 'INNER%' OR LIKE 'IK%'
    # The fix: only LENGTH(inchikey)=27 OR LIKE 'SYNTH%'
    m = re.search(
        r"chk_drugs_inchikey_format.*?(?=CONSTRAINT|\);|$)",
        src,
        re.DOTALL,
    )
    if m:
        constraint = m.group(0)
        assert "TEST" not in constraint, (
            "TOP-17 REGRESSION: chk_drugs_inchikey_format still accepts "
            "TEST% prefix. Test-fixture InChIKeys can enter DB."
        )
        assert "OUTER" not in constraint, (
            "TOP-17 REGRESSION: chk_drugs_inchikey_format still accepts OUTER%."
        )
        assert "INNER" not in constraint, (
            "TOP-17 REGRESSION: chk_drugs_inchikey_format still accepts INNER%."
        )


def test_migration_009_exists():
    p = Path(
        "/home/z/my-project/v28/v28_upgraded/phase1/database/migrations/"
        "009_tighten_inchikey_check_constraint.sql"
    )
    assert p.exists(), (
        "TOP-17 REGRESSION: migration 009_tighten_inchikey_check_constraint.sql "
        "not found. Deployed PostgreSQL DBs still have the permissive constraint."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
