"""v35 regression tests for HIGH-severity fixes beyond the 15 CRITICAL fixes.

Each test verifies a specific HIGH fix from the v35 forensic re-audit.
If any test fails, the corresponding fix was reverted or broken.

Run with: pytest tests/v35_regression_tests/test_v35_high_fixes.py -v
"""
import os
import sys
import re
import inspect
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
PHASE1 = PROJECT_ROOT / "phase1"
PHASE2 = PROJECT_ROOT / "phase2"
for p in (str(PHASE1), str(PHASE2)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ═══ Phase 1 HIGH Fixes ═══════════════════════════════════════════════════

def test_p1_high_2_string_id_regex_accepts_any_taxid():
    """HIGH #2: STRING ID regex must accept any taxid, not just 9606."""
    from pipelines.uniprot_pipeline import _STRING_ID_RE
    assert _STRING_ID_RE.match("9606.ENSP00000269567"), "Human STRING ID should match"
    assert _STRING_ID_RE.match("10090.ENSP00000000123"), "Mouse STRING ID should match"

def test_p1_high_3_gene_symbol_regex_accepts_title_case():
    """HIGH #3: Gene symbol regex must accept Title-Case for non-human genes."""
    from pipelines.uniprot_pipeline import _HGNC_SYMBOL_RE
    assert _HGNC_SYMBOL_RE.match("TP53"), "Human all-caps gene symbol should match"
    assert _HGNC_SYMBOL_RE.match("Tp53"), "Mouse title-case gene symbol should match"

def test_p1_high_4_aa_sequence_includes_gap_char():
    """HIGH #4: AA sequence regex must include '-' gap character consistently."""
    from database.models import _SEQUENCE_RE
    assert _SEQUENCE_RE.match("MSKLLPQV-LRT"), "AA sequence with gap char should be accepted"

def test_p1_high_5_omim_score_map_aligned():
    """HIGH #5: OMIM categorical map must align between pipeline and validator."""
    import cleaning.missing_values as _mv
    src = inspect.getsource(_mv)
    # The fix changed {1: 0.5, 2: 0.7, 3: 0.9} to {1: 0.5, 2: 0.6, 3: 0.9}
    # Check the actual MAP DEFINITION line (not comments mentioning the old value)
    lines = src.split("\n")
    map_line = None
    for line in lines:
        if "_OMIM_CATEGORICAL_MAP" in line and "=" in line and "{" in line:
            map_line = line.strip()
            break
    assert map_line is not None, "Could not find _OMIM_CATEGORICAL_MAP definition"
    assert "2: 0.6" in map_line, f"OMIM mk=2 should be 0.6 in map definition: {map_line}"
    assert "2: 0.7" not in map_line, f"OMIM mk=2 should NOT be 0.7: {map_line}"

def test_p1_high_7_disgenet_omim_regex_4_to_7_digits():
    """HIGH #7: DisGeNET OMIM regex must accept 4-7 digit MIM numbers."""
    from pipelines.disgenet_pipeline import _RE_OMIM
    assert _RE_OMIM.match("100100"), "6-digit OMIM should match"
    assert _RE_OMIM.match("1234"), "4-digit OMIM should match"

def test_p1_high_8_drugbank_synth_no_hyphen():
    """HIGH #8: SYNTH key check must use startswith('SYNTH') not 'SYNTH-'."""
    import pipelines.drugbank_pipeline as _dp
    src = inspect.getsource(_dp)
    assert 'startswith("SYNTH-")' not in src, \
        "CRITICAL REGRESSION: startswith('SYNTH-') still present"


# ═══ Phase 2 Bridge HIGH Fixes ═══════════════════════════════════════════

def test_p2_bridge_high_2_source_priority_has_drugbank_indication():
    """HIGH #2: SOURCE_PRIORITY_MAP must have 'drugbank_indication' key."""
    from drugos_graph.kg_builder import SOURCE_PRIORITY_MAP
    assert "drugbank_indication" in SOURCE_PRIORITY_MAP

def test_p2_bridge_high_6_dev_smoke_test_documented():
    """HIGH #6: dev_smoke_test_pass must have companion fields."""
    from drugos_graph import run_pipeline
    src = inspect.getsource(run_pipeline)
    assert "pipeline_ran_end_to_end" in src
    assert "dev_relaxed_criteria_passed" in src


# ═══ Phase 2 ML HIGH Fixes ═══════════════════════════════════════════════

def test_p2_ml_high_1_entity_embeddings_docstring_honest():
    """HIGH #1: entity_embeddings docstring must not claim 'concatenates'."""
    from drugos_graph.graph_transformer_model import GraphTransformerModel
    docstring = GraphTransformerModel.entity_embeddings.__doc__ or ""
    assert "concatenates them in node-type order" not in docstring

def test_p2_ml_high_9_negative_sampler_precomputes_degree():
    """HIGH #9: NegativeSampler must precompute degree Counter."""
    from drugos_graph.negative_sampling import NegativeSampler
    src = inspect.getsource(NegativeSampler)
    assert "_drug_degree_counter" in src or "_drug_degree" in src

def test_p2_ml_high_10_leakage_detection_vectorized():
    """HIGH #10: _detect_leakage must use vectorized approach."""
    from drugos_graph.evaluation import _detect_leakage
    src = inspect.getsource(_detect_leakage)
    assert "np.isin" in src or "set(" in src

def test_p2_ml_high_11_chemberta_truncation_filters_before_encode():
    """HIGH #11: on_truncate='skip' must filter batch BEFORE encoding."""
    from drugos_graph.chemberta_encoder import encode_smiles
    src = inspect.getsource(encode_smiles)
    assert "keep_mask" in src

def test_p2_ml_high_12_chemberta_oom_while_loop():
    """HIGH #12: OOM recovery must use while loop."""
    from drugos_graph.chemberta_encoder import encode_smiles
    src = inspect.getsource(encode_smiles)
    assert "while i <" in src or "while i <len" in src


# ═══ Phase 2 Loaders HIGH Fixes ══════════════════════════════════════════

def test_p2_loaders_high_1_chembl_inchikey_normalization_param():
    """HIGH #1: chembl_to_edge_records_from_phase1 must accept canonical map."""
    from drugos_graph.chembl_loader import chembl_to_edge_records_from_phase1
    sig = inspect.signature(chembl_to_edge_records_from_phase1)
    assert "compound_canonical_map" in sig.parameters or "canonical_map" in sig.parameters

def test_p2_loaders_high_2_drugbank_canonical_map_param():
    """HIGH #2: drugbank_to_target_edges_from_phase1 must accept drug_canonical_map."""
    from drugos_graph.drugbank_parser import drugbank_to_target_edges_from_phase1
    sig = inspect.signature(drugbank_to_target_edges_from_phase1)
    assert "drug_canonical_map" in sig.parameters

def test_p2_loaders_high_3_stitch_docstring_correct():
    """HIGH #3: STITCH docstring must correctly say CIDm=FLAT, CIDs=STEREO."""
    from drugos_graph import stitch_loader
    src = inspect.getsource(stitch_loader)
    # Check the MAIN description (first 58 lines — before the fix-explanation comments)
    lines = src.split("\n")
    main_desc = "\n".join(lines[:58])
    assert "CIDm00002244`` (FLAT" in main_desc or "CIDm00002244`` (flat" in main_desc, \
        "STITCH docstring main description should say CIDm=FLAT"
    assert "CIDm00002244`` (stereo-specific" not in main_desc, \
        "STITCH docstring main description still inverts CIDm/CIDs"

def test_p2_loaders_high_4_step8_uses_phase1_csv():
    """HIGH #4: step8 must use Phase 1's uniprot_proteins.csv when available."""
    from drugos_graph import run_pipeline
    src = inspect.getsource(run_pipeline)
    assert "parse_uniprot_entries_from_phase1_csv" in src

def test_p2_loaders_high_5_geo_loader_standard_schema():
    """HIGH #5: geo_loader must use src_type/rel_type/dst_type."""
    from drugos_graph import geo_loader
    src = inspect.getsource(geo_loader)
    assert "src_type" in src and "rel_type" in src and "dst_type" in src


# ═══ Neo4j Persistence + E2E ═════════════════════════════════════════════

def test_neo4j_persistence_staged_graph_json():
    """Verify staged graph is persisted to disk."""
    staged_path = PHASE2 / "data" / "processed" / "staged_graph.json"
    if not staged_path.exists():
        import subprocess
        subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "run_unified.py"), "--no-full-pipeline"],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=120,
        )
    assert staged_path.exists(), "staged_graph.json not created"
    import json
    with open(staged_path) as f:
        data = json.load(f)
    assert sum(data["node_counts_by_type"].values()) > 0

def test_e2e_pipeline_runs_without_crash():
    """Verify pipeline runs end-to-end without Python crashes."""
    import subprocess
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "run_unified.py"), "--no-full-pipeline"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"Pipeline exited {result.returncode}. stderr: {result.stderr[-500:]}"
    # Output goes to stderr (logging), not stdout
    combined = result.stdout + result.stderr
    assert "UNIFIED RUN COMPLETE" in combined, \
        f"Pipeline didn't complete. Combined output: {combined[-500:]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
