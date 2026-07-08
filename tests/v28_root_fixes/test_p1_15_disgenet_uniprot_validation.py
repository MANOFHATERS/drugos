"""P1-15: DisGeNET _api_uniprot_id must be validated before assignment.

ROOT-CAUSE: API-provided UniProt IDs assigned without format validation.
~5-10% invalid IDs enter DB.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase1/pipelines/disgenet_pipeline.py"
)


def test_api_uniprot_id_validated_before_assignment():
    src = _FILE.read_text()
    # The fix must validate _api_uniprot_id against UNIPROT_ID_PATTERN
    # before assigning to df["uniprot_id"].
    assert "UNIPROT_ID_PATTERN" in src, (
        "P1-15 REGRESSION: disgenet_pipeline.py does not import or use "
        "UNIPROT_ID_PATTERN. API-provided UniProt IDs are not validated."
    )
    # Look for validation logic near _api_uniprot_id assignment
    assert re.search(
        r"(_api_uniprot_id|api_uniprot_id).*?UNIPROT_ID_PATTERN",
        src,
        re.DOTALL,
    ), (
        "P1-15 REGRESSION: _api_uniprot_id is not validated against "
        "UNIPROT_ID_PATTERN before assignment."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
