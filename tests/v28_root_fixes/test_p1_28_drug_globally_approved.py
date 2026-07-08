"""P1-28: Drug model must have is_globally_approved column.

ROOT-CAUSE: ChEMBL pipeline emits is_globally_approved but Drug model
didn't have it. Always NULL in DB.

NOTE: This test uses importlib to load models.py DIRECTLY from the v28
path, bypassing sys.modules caching issues.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


def _load_drug_model_fresh():
    """Load models.py directly from the v28 path, bypassing sys.modules cache."""
    models_path = Path(
        "/home/z/my-project/v28/v28_upgraded/phase1/database/models.py"
    )
    phase1 = str(models_path.parent.parent)
    if phase1 not in sys.path:
        sys.path.insert(0, phase1)
    # Remove any cached database modules
    to_remove = [k for k in sys.modules if k.startswith("database")]
    for k in to_remove:
        del sys.modules[k]
    # Now import fresh
    from database.models import Drug  # noqa: E402
    return Drug


def test_drug_model_has_is_globally_approved():
    Drug = _load_drug_model_fresh()
    cols = {c.name for c in Drug.__table__.columns}
    assert "is_globally_approved" in cols, (
        "P1-28 REGRESSION: Drug model does not have is_globally_approved "
        "column. ChEMBL's globally-approved flag is silently dropped."
    )


def test_migration_008_exists():
    p = Path(
        "/home/z/my-project/v28/v28_upgraded/phase1/database/migrations/"
        "008_drug_is_globally_approved.sql"
    )
    assert p.exists(), (
        "P1-28 REGRESSION: migration 008_drug_is_globally_approved.sql not found."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
