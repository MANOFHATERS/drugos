"""P2-L-10: drugbank_to_node_records_from_phase1 must include "id" field.

ROOT-CAUSE: omitted "id" field. kg_builder requires it. 100% nodes
dead-lettered (latent — function was dead code in v27).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/drugbank_parser.py"
)


def test_drugbank_from_phase1_node_has_id_field():
    src = _FILE.read_text()
    # Find the function body
    m = re.search(
        r"def\s+drugbank_to_node_records_from_phase1\b[^:]*:(.*?)(?=\ndef\s|\nclass\s|\Z)",
        src,
        re.DOTALL,
    )
    assert m, "P2-L-10 setup: cannot find drugbank_to_node_records_from_phase1"
    body = m.group(1)
    # Must have "id" field in the node dict
    assert '"id"' in body or "'id'" in body, (
        "P2-L-10 REGRESSION: drugbank_to_node_records_from_phase1 does not "
        "include 'id' field in node dict. kg_builder requires it."
    )


def test_drugbank_from_phase1_node_id_uses_inchikey_or_drugbank_id():
    src = _FILE.read_text()
    m = re.search(
        r"def\s+drugbank_to_node_records_from_phase1\b[^:]*:(.*?)(?=\ndef\s|\nclass\s|\Z)",
        src,
        re.DOTALL,
    )
    body = m.group(1)
    # The id should prefer inchikey, fall back to drugbank_id
    assert "inchikey" in body.lower() and "drugbank_id" in body.lower(), (
        "P2-L-10 REGRESSION: node id does not use inchikey (preferred) "
        "or drugbank_id (fallback)."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
