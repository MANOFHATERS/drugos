"""P1-ER-6: RejectedRecord ORM model must exist.

ROOT-CAUSE BEING VERIFIED:
  Migration 001 created the rejected_records table but no ORM model
  existed for it. SQLite path didn't have the table; PostgreSQL had a
  dead table.
"""
from __future__ import annotations

import sys

import pytest

sys.path.insert(0, "/home/z/my-project/v28/v28_upgraded/phase1")

from database.models import RejectedRecord  # noqa: E402


def test_rejected_record_tablename():
    assert RejectedRecord.__tablename__ == "rejected_records"


def test_rejected_record_columns():
    cols = {c.name for c in RejectedRecord.__table__.columns}
    expected = {
        "id", "source_table", "source_pipeline", "raw_data",
        "rejection_reason", "rejection_type", "pipeline_run_id", "created_at",
    }
    missing = expected - cols
    assert not missing, f"P1-ER-6 REGRESSION: RejectedRecord missing columns {missing}"


def test_rejected_record_can_be_instantiated():
    """Quick smoke test: can construct an instance."""
    rec = RejectedRecord(
        source_table="drugs",
        source_pipeline="chembl",
        rejection_reason="bad inchikey",
        rejection_type="format_error",
    )
    assert rec.source_table == "drugs"
    assert rec.rejection_type == "format_error"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
