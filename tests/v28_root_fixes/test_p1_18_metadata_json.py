"""P1-18: PipelineRun model must have metadata_json column.

ROOT-CAUSE: metadata_json (run_id, sha256, dq_metrics) computed but
never persisted. FDA 21 CFR Part 11 audit traceability broken.

NOTE: This test uses importlib.util.spec_from_file_location to load
models.py DIRECTLY from the v28 path, bypassing any sys.path caching
issues that occur when running after v27 tests.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MODELS_PATH = Path(
    "/home/z/my-project/v28/v28_upgraded/phase1/database/models.py"
)


def _load_models_fresh():
    """Load models.py directly from the v28 path, bypassing sys.modules cache."""
    # First, ensure phase1 is on sys.path so that models.py's relative
    # imports (from .base import Base, etc.) work
    phase1 = str(_MODELS_PATH.parent.parent)
    if phase1 not in sys.path:
        sys.path.insert(0, phase1)
    # Remove any cached database modules
    to_remove = [k for k in sys.modules if k.startswith("database")]
    for k in to_remove:
        del sys.modules[k]
    # Now import fresh
    from database.models import PipelineRun  # noqa: E402
    return PipelineRun


def test_pipeline_run_has_metadata_json_column():
    PipelineRun = _load_models_fresh()
    cols = {c.name for c in PipelineRun.__table__.columns}
    assert "metadata_json" in cols, (
        "P1-18 REGRESSION: PipelineRun model does not have metadata_json "
        "column. Provenance (run_id, sha256, dq_metrics) is silently dropped."
    )


def test_migration_007_exists():
    p = Path(
        "/home/z/my-project/v28/v28_upgraded/phase1/database/migrations/"
        "007_pipeline_run_metadata.sql"
    )
    assert p.exists(), (
        "P1-18 REGRESSION: migration 007_pipeline_run_metadata.sql not found."
    )
    sql = p.read_text()
    assert "metadata_json" in sql.lower(), (
        "P1-18 REGRESSION: migration 007 does not add metadata_json column."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
