"""
Test for Gap #3 Root Fix — Compound→Protein 90% loss (DrugBank interactions)
==============================================================================

BEFORE FIX:
- drugbank_interactions.csv.gz contains 3,711 edges
- 3,640 edges dropped with reason 'drug_not_in_compound_nodes'
- Only 4,477 edges survived (all from ChEMBL, 0 from DrugBank interactions)
- ROOT CAUSE: drug_canonical_map built ONLY from staged.compound_nodes
  (which come from drugbank_drugs.csv). Any drugbank_id in interactions
  that wasn't in drugs.csv was rejected.

AFTER FIX:
- Before building drug_canonical_map, scan interactions for drugbank_ids
  NOT in compound_nodes
- Create minimal stub Compound nodes for missing IDs (marked _is_stub=True)
- 100% of DrugBank interactions preserved
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

# Ensure phase2 is importable
HERE = Path(__file__).resolve().parent
PHASE2_ROOT = HERE.parent
sys.path.insert(0, str(PHASE2_ROOT))

from drugos_graph.phase1_bridge import stage_phase1_to_phase2, Phase1StagedData


class TestGap3_CompoundProteinEdgeLoss:
    """Behavioral tests for Gap #3 root fix."""

    def test_stub_nodes_created_for_missing_drugbank_ids(self):
        """
        When interactions reference drugbank_ids NOT in drugbank_drugs.csv,
        stub Compound nodes must be created to preserve edges.
        """
        # Simulate drugbank_drugs.csv with only 2 drugs
        drugs_df = pd.DataFrame([
            {"drugbank_id": "DB00001", "name": "Drug A", "inchikey": "AAAA", "smiles": "C", "is_fda_approved": True, "is_withdrawn": False},
            {"drugbank_id": "DB00002", "name": "Drug B", "inchikey": "BBBB", "smiles": "CC", "is_fda_approved": True, "is_withdrawn": False},
        ])
        
        # Simulate drugbank_interactions.csv.gz with 4 drugs (2 missing from drugs.csv)
        interactions_df = pd.DataFrame([
            {"drugbank_id": "DB00001", "uniprot_id": "P12345", "action_type": "inhibitor", "target_name": "Target1", "organism": "Human"},
            {"drugbank_id": "DB00002", "uniprot_id": "P12346", "action_type": "activator", "target_name": "Target2", "organism": "Human"},
            {"drugbank_id": "DB00003", "uniprot_id": "P12347", "action_type": "inhibitor", "target_name": "Target3", "organism": "Human"},  # MISSING from drugs
            {"drugbank_id": "DB00004", "uniprot_id": "P12348", "action_type": "binder", "target_name": "Target4", "organism": "Human"},   # MISSING from drugs
        ])
        
        frames = {
            "drugs": drugs_df,
            "interactions": interactions_df,
            "omim_gda": pd.DataFrame(),  # Empty for this test
        }
        
        staged = stage_phase1_to_phase2(frames, run_id="test-gap3-fix")
        
        # Verify stub nodes were created for DB00003 and DB00004
        compound_ids = {n["id"] for n in staged.compound_nodes}
        assert "DB00001" in compound_ids, "Existing drug DB00001 should be present"
        assert "DB00002" in compound_ids, "Existing drug DB00002 should be present"
        assert "DB00003" in compound_ids, "Stub node for DB00003 should be created"
        assert "DB00004" in compound_ids, "Stub node for DB00004 should be created"
        
        # Verify stub nodes are marked with _is_stub=True
        stub_nodes = [n for n in staged.compound_nodes if n.get("_is_stub")]
        assert len(stub_nodes) == 2, f"Expected 2 stub nodes, got {len(stub_nodes)}"
        stub_ids = {n["id"] for n in stub_nodes}
        assert stub_ids == {"DB00003", "DB00004"}, f"Stub IDs mismatch: {stub_ids}"

    def test_all_interaction_edges_preserved(self):
        """
        All edges from drugbank_interactions must be preserved, even for
        drugs not in drugbank_drugs.csv.
        """
        drugs_df = pd.DataFrame([
            {"drugbank_id": "DB00001", "name": "Drug A", "inchikey": "AAAA", "smiles": "C", "is_fda_approved": True, "is_withdrawn": False},
        ])
        
        # 5 interactions, 4 referencing drugs NOT in drugs.csv
        interactions_df = pd.DataFrame([
            {"drugbank_id": "DB00001", "uniprot_id": "P12345", "action_type": "inhibitor", "target_name": "Target1", "organism": "Human"},
            {"drugbank_id": "DB00002", "uniprot_id": "P12346", "action_type": "activator", "target_name": "Target2", "organism": "Human"},
            {"drugbank_id": "DB00003", "uniprot_id": "P12347", "action_type": "inhibitor", "target_name": "Target3", "organism": "Human"},
            {"drugbank_id": "DB00004", "uniprot_id": "P12348", "action_type": "binder", "target_name": "Target4", "organism": "Human"},
            {"drugbank_id": "DB00005", "uniprot_id": "P12349", "action_type": "inhibitor", "target_name": "Target5", "organism": "Human"},
        ])
        
        frames = {
            "drugs": drugs_df,
            "interactions": interactions_df,
            "omim_gda": pd.DataFrame(),
        }
        
        staged = stage_phase1_to_phase2(frames, run_id="test-gap3-fix")
        
        # Count all Compound→Protein edges
        cp_edge_types = [
            ("Compound", "targets", "Protein"),
            ("Compound", "inhibits", "Protein"),
            ("Compound", "activates", "Protein"),
            ("Compound", "allosterically_modulates", "Protein"),
            ("Compound", "metabolized_by", "Protein"),
            ("Compound", "unknown", "Protein"),
        ]
        
        total_cp_edges = sum(len(staged.edges.get(et, [])) for et in cp_edge_types)
        
        # All 5 interactions should produce edges (no drops)
        assert total_cp_edges == 5, f"Expected 5 Compound→Protein edges, got {total_cp_edges}"
        
        # No dropped edges should be recorded
        if hasattr(staged, 'dead_letter_edges'):
            dropped = [e for e in staged.dead_letter_edges if e.get("reason") == "drug_not_in_compound_nodes"]
            assert len(dropped) == 0, f"Expected 0 dropped edges, but {len(dropped)} were dropped: {dropped[:3]}"

    def test_no_regression_existing_drugs(self):
        """
        Drugs that ARE in drugbank_drugs.csv should work exactly as before
        (no regression). Their canonical IDs should come from the drugs.csv,
        not be stubs.
        """
        drugs_df = pd.DataFrame([
            {"drugbank_id": "DB00001", "name": "Drug A", "inchikey": "INCHIKEY123", "smiles": "C", "is_fda_approved": True, "is_withdrawn": False},
        ])
        
        interactions_df = pd.DataFrame([
            {"drugbank_id": "DB00001", "uniprot_id": "P12345", "action_type": "inhibitor", "target_name": "Target1", "organism": "Human"},
        ])
        
        frames = {
            "drugs": drugs_df,
            "interactions": interactions_df,
            "omim_gda": pd.DataFrame(),
        }
        
        staged = stage_phase1_to_phase2(frames, run_id="test-no-regression")
        
        # Should have exactly 1 compound node (from drugs.csv, NOT a stub)
        assert len(staged.compound_nodes) == 1
        node = staged.compound_nodes[0]
        assert node["drugbank_id"] == "DB00001"
        assert node.get("inchikey") == "INCHIKEY123"
        assert node.get("_is_stub") is None or node.get("_is_stub") is False, \
            "Existing drug should NOT be marked as stub"

    def test_empty_interactions_handled_gracefully(self):
        """
        Edge case: empty interactions DataFrame should not crash.
        """
        drugs_df = pd.DataFrame([
            {"drugbank_id": "DB00001", "name": "Drug A", "inchikey": "AAAA", "smiles": "C", "is_fda_approved": True, "is_withdrawn": False},
        ])
        
        frames = {
            "drugs": drugs_df,
            "interactions": pd.DataFrame(),  # Empty
            "omim_gda": pd.DataFrame(),
        }
        
        staged = stage_phase1_to_phase2(frames, run_id="test-empty-interactions")
        
        # Should have 1 compound node (from drugs.csv), no stubs
        assert len(staged.compound_nodes) == 1
        assert staged.compound_nodes[0]["drugbank_id"] == "DB00001"
        
        # No edges should be produced
        total_edges = sum(len(v) for v in staged.edges.values())
        assert total_edges == 0

    def test_duplicate_drugbank_ids_deduped(self):
        """
        Multiple interactions for the same drugbank_id should NOT create
        duplicate stub nodes.
        """
        drugs_df = pd.DataFrame()  # Empty drugs
        
        interactions_df = pd.DataFrame([
            {"drugbank_id": "DB00003", "uniprot_id": "P12345", "action_type": "inhibitor", "target_name": "Target1", "organism": "Human"},
            {"drugbank_id": "DB00003", "uniprot_id": "P12346", "action_type": "activator", "target_name": "Target2", "organism": "Human"},
            {"drugbank_id": "DB00003", "uniprot_id": "P12347", "action_type": "binder", "target_name": "Target3", "organism": "Human"},
        ])
        
        frames = {
            "drugs": drugs_df,
            "interactions": interactions_df,
            "omim_gda": pd.DataFrame(),
        }
        
        staged = stage_phase1_to_phase2(frames, run_id="test-dedup-stubs")
        
        # Should create exactly 1 stub node for DB00003 (not 3)
        db00003_nodes = [n for n in staged.compound_nodes if n["drugbank_id"] == "DB00003"]
        assert len(db00003_nodes) == 1, f"Expected 1 stub node for DB00003, got {len(db00003_nodes)}"
        
        # Should have 3 edges (one per interaction)
        cp_edge_types = [
            ("Compound", "targets", "Protein"),
            ("Compound", "inhibits", "Protein"),
            ("Compound", "activates", "Protein"),
            ("Compound", "allosterically_modulates", "Protein"),
            ("Compound", "metabolized_by", "Protein"),
            ("Compound", "unknown", "Protein"),
        ]
        total_cp_edges = sum(len(staged.edges.get(et, [])) for et in cp_edge_types)
        assert total_cp_edges == 3, f"Expected 3 edges for DB00003, got {total_cp_edges}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
