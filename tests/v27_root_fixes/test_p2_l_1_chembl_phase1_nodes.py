"""P2-L-1: chembl_to_node_records_from_phase1 must return non-empty nodes.

ROOT-CAUSE BEING VERIFIED:
  The function blindly delegated to chembl_to_node_records which required
  a `drug_chembl_id` column (raw SQLite SQL alias). Phase 1's
  chembl_drugs.csv has `chembl_id` only → returned 0 nodes.
"""
from __future__ import annotations

import sys

import pandas as pd
import pytest

sys.path.insert(0, "/home/z/my-project/v28/v28_upgraded/phase2")

from drugos_graph.chembl_loader import chembl_to_node_records_from_phase1  # noqa: E402


def test_chembl_from_phase1_returns_nodes_on_real_fixture():
    """Call chembl_to_node_records_from_phase1 on the actual Phase 1 CSV."""
    df = pd.read_csv(
        "/home/z/my-project/v28/v28_upgraded/phase1/processed_data/chembl_drugs.csv"
    )
    nodes = chembl_to_node_records_from_phase1(df)
    assert len(nodes) > 0, (
        "P2-L-1 REGRESSION: chembl_to_node_records_from_phase1 returned 0 nodes "
        "on the real Phase 1 fixture. The function must read `chembl_id` "
        "directly, not delegate to chembl_to_node_records which requires "
        "`drug_chembl_id`."
    )


def test_chembl_from_phase1_node_has_id_field():
    df = pd.read_csv(
        "/home/z/my-project/v28/v28_upgraded/phase1/processed_data/chembl_drugs.csv"
    )
    nodes = chembl_to_node_records_from_phase1(df)
    assert nodes, "P2-L-1 setup: no nodes returned"
    first = nodes[0]
    assert "id" in first, "P2-L-1 REGRESSION: node dict missing 'id' field"
    assert first["id"], "P2-L-1 REGRESSION: node 'id' is empty"


def test_chembl_from_phase1_node_has_chembl_id_and_inchikey():
    df = pd.read_csv(
        "/home/z/my-project/v28/v28_upgraded/phase1/processed_data/chembl_drugs.csv"
    )
    nodes = chembl_to_node_records_from_phase1(df)
    first = nodes[0]
    assert "chembl_id" in first
    assert "inchikey" in first
    # InChIKey must be uppercase (P2-B-2 fix)
    if first.get("inchikey"):
        assert first["inchikey"] == first["inchikey"].upper(), (
            "P2-L-1 / P2-B-2 REGRESSION: InChIKey not uppercased"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
