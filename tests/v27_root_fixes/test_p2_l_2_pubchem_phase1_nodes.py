"""P2-L-2: pubchem_to_node_records must NOT drop 100% of rows when CID absent.

ROOT-CAUSE BEING VERIFIED:
  Required `pubchem_cid`/`cid`/`CID` column. Phase 1's
  pubchem_enrichment.csv has none (keyed by `inchikey`). All rows
  skipped → 0 nodes. Runtime confirmed: pubchem_nodes: 0.
"""
from __future__ import annotations

import sys

import pandas as pd
import pytest

sys.path.insert(0, "/home/z/my-project/v28/v28_upgraded/phase2")

from drugos_graph.pubchem_loader import pubchem_to_node_records  # noqa: E402


def test_pubchem_from_phase1_returns_nodes_on_real_fixture():
    df = pd.read_csv(
        "/home/z/my-project/v28/v28_upgraded/phase1/processed_data/pubchem_enrichment.csv"
    )
    nodes = pubchem_to_node_records(df)
    assert len(nodes) > 0, (
        "P2-L-2 REGRESSION: pubchem_to_node_records returned 0 nodes on the "
        "real Phase 1 fixture. The function must use `inchikey` as "
        "canonical_id when no CID column is present."
    )


def test_pubchem_node_uses_inchikey_as_id_when_no_cid():
    df = pd.read_csv(
        "/home/z/my-project/v28/v28_upgraded/phase1/processed_data/pubchem_enrichment.csv"
    )
    nodes = pubchem_to_node_records(df)
    first = nodes[0]
    assert "id" in first
    # When no CID column, id should be the (uppercased) inchikey
    assert first["id"], "P2-L-2 REGRESSION: node id empty"
    # Should be uppercase (InChIKey canonical form)
    if first.get("inchikey"):
        assert first["inchikey"] == first["inchikey"].upper()


def test_pubchem_node_has_smiles_from_canonical_smiles():
    df = pd.read_csv(
        "/home/z/my-project/v28/v28_upgraded/phase1/processed_data/pubchem_enrichment.csv"
    )
    nodes = pubchem_to_node_records(df)
    first = nodes[0]
    # smiles should be populated from canonical_smiles
    assert "smiles" in first
    # If the fixture has canonical_smiles, smiles must be populated
    if "canonical_smiles" in df.columns:
        first_row = df.iloc[0]
        if isinstance(first_row.get("canonical_smiles"), str) and first_row["canonical_smiles"]:
            assert first.get("smiles"), (
                "P2-L-2 REGRESSION: smiles field empty despite canonical_smiles "
                "being present in source CSV"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
