"""P1-21: chembl_activities_clean.csv must be in schema v1.json.

ROOT-CAUSE: 8th CSV emitted by ChEMBL pipeline but not in schema.
Downstream consumers reading schema miss it entirely.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_SCHEMA = Path(
    "/home/z/my-project/v28/v28_upgraded/phase1/pipelines/schema/v1.json"
)


def test_schema_includes_chembl_activities_clean():
    schema = json.loads(_SCHEMA.read_text())
    props = schema.get("properties", {})
    assert "chembl_activities_clean.csv" in props, (
        "P1-21 REGRESSION: schema/v1.json does not include "
        "chembl_activities_clean.csv. Downstream consumers reading the "
        "schema miss ChEMBL DPI data entirely."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
