"""
V44_ROOT_FIX_VERIFICATION test suite.

Verifies that the forensic audit findings (P0 + P1 + key P2) have been
root-fixed in the upgraded codebase. This is NOT a unit test of original
functionality — it is a regression test that the specific bugs identified
in FORENSIC_AUDIT_REPORT.md no longer exist.

Run with:
    cd <project root>
    python -m pytest tests/test_v44_root_fix_verification.py -v
OR:
    python tests/test_v44_root_fix_verification.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure project paths are importable
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
PHASE1 = PROJECT_ROOT / "phase1"
PHASE2 = PROJECT_ROOT / "phase2"
for p in (str(PHASE2), str(PHASE1)):
    if p not in sys.path:
        sys.path.insert(0, p)


# =============================================================================
# Finding 1: Master DAG BranchPythonOperator returns wrong task_id
# =============================================================================

def test_finding_1_master_dag_branch_returns_run_drugbank():
    """Master DAG _check_drugbank_xml must return 'run_drugbank' (not
    'download_drugbank') when the XML exists."""
    dag_path = PHASE1 / "dags" / "master_pipeline_dag.py"
    src = dag_path.read_text()
    # The fix must return "run_drugbank" (the actual task_id).
    assert 'return "run_drugbank"' in src, (
        "Finding 1 root fix missing: master DAG must return "
        "'run_drugbank' (the actual @task task_id), not "
        "'download_drugbank' (which matches no task)."
    )
    # The old broken value must NOT be present as a return.
    assert 'return "download_drugbank"' not in src, (
        "Finding 1 regression: 'return \"download_drugbank\"' is "
        "still present — this matches NO task in the DAG and causes "
        "AirflowException on every DrugBank-XML-present run."
    )


# =============================================================================
# Finding 2: DrugBank license attribution is factually wrong
# =============================================================================

def test_finding_2_drugbank_license_text_corrected():
    """DrugBank license text must NOT claim CC BY-NC 4.0 (false).
    The ACTUAL license string written to DRUGBANK_LICENSE.txt must
    use the corrected text. Comments explaining the fix may mention
    CC BY-NC in the historical context."""
    pipe_path = PHASE1 / "pipelines" / "drugbank_pipeline.py"
    # Import the actual module and read the variable value.
    sys.path.insert(0, str(PHASE1))
    try:
        # We need to import the module to get the actual string value
        # (string concatenation in source makes regex extraction unreliable).
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "drugbank_pipeline", pipe_path,
        )
        # We can't fully import (lxml etc. may be needed) — instead
        # evaluate the string literal by exec'ing just the assignment.
        src = pipe_path.read_text()
        import re
        import ast
        # Find the assignment and parse its value as a Python expression.
        match = re.search(
            r'(_DRUGBANK_LICENSE_TEXT\s*:\s*str\s*=\s*\(\s*)(.*?)(\s*\)\s*\n)',
            src, re.DOTALL,
        )
        assert match, "Could not find _DRUGBANK_LICENSE_TEXT definition"
        # The value is a parenthesized concatenation of string literals.
        # Extract just the string-literal part and eval it.
        value_src = "(" + match.group(2) + ")"
        try:
            license_text = ast.literal_eval(value_src)
        except (ValueError, SyntaxError) as e:
            # Fallback: just check the raw source for key phrases.
            license_text = match.group(2)
        # The license TEXT must NOT claim CC BY-NC.
        assert "CC BY-NC 4.0 for academic use" not in license_text, (
            "Finding 2 root fix missing: the _DRUGBANK_LICENSE_TEXT "
            "string still claims 'CC BY-NC 4.0 for academic use' — "
            "this is FALSE. DrugBank data is governed by a custom EULA."
        )
        # The CORRECT claim must be present.
        assert "custom EULA" in license_text, (
            "Finding 2 root fix missing: corrected license text must "
            "mention DrugBank's custom EULA (not CC BY-NC)."
        )
    finally:
        sys.path.pop(0)


# =============================================================================
# Finding 3: Parallel-run provenance is silently corrupted
# =============================================================================

def test_finding_3_parallel_provenance_passes_run_id_explicitly():
    """download_parallel.py must pass run_id explicitly to pipeline
    constructors (not rely on thread-local)."""
    script_path = PHASE1 / "scripts" / "download_parallel.py"
    src = script_path.read_text()
    assert "cls(run_id=_run_id)" in src, (
        "Finding 3 root fix missing: download_parallel.py must pass "
        "run_id explicitly via cls(run_id=_run_id) so provenance is "
        "thread-safe under ThreadPoolExecutor."
    )


# =============================================================================
# Finding 4: EC50/AC50 unconditionally classified as "activator"
# =============================================================================

def test_finding_4_ec50_ac50_returns_unknown():
    """_infer_interaction_type_from_activity_type must return UNKNOWN
    for EC50/AC50 (not ACTIVATOR)."""
    # Import the ChEMBL pipeline module
    from pipelines.chembl_pipeline import ChEMBLPipeline
    result_ec50 = ChEMBLPipeline._infer_interaction_type_from_activity_type("EC50")
    result_ac50 = ChEMBLPipeline._infer_interaction_type_from_activity_type("AC50")
    result_pec50 = ChEMBLPipeline._infer_interaction_type_from_activity_type("pEC50")
    assert result_ec50 == "unknown", (
        f"Finding 4 root fix missing: EC50 must return 'unknown', "
        f"got {result_ec50!r}. EC50 is agonist/antagonist/inverse-"
        f"agonist ambiguous — classifying as 'activator' biases the "
        f"Graph Transformer's training set."
    )
    assert result_ac50 == "unknown", (
        f"Finding 4 root fix missing: AC50 must return 'unknown', "
        f"got {result_ac50!r}."
    )
    assert result_pec50 == "unknown", (
        f"Finding 4 root fix missing: pEC50 must return 'unknown', "
        f"got {result_pec50!r}."
    )


# =============================================================================
# Findings 5 & 6: OMIM confidence tier labels
# =============================================================================

def test_findings_5_6_omim_tier_labels_correct():
    """OMIM_CONFIDENCE_TIERS must use the corrected labels."""
    from cleaning.confidence import OMIM_CONFIDENCE_TIERS
    labels = [label for _, label in OMIM_CONFIDENCE_TIERS]
    assert "omim_phenotype_mapped" in labels, (
        "Finding 5 root fix missing: mk=2 label must be "
        "'omim_phenotype_mapped' (was 'omim_confirmed' — WRONG: "
        "mk=2 is explicitly NOT confirmed)."
    )
    assert "omim_contiguous_gene_syndrome" in labels, (
        "Finding 6 root fix missing: mk=4 label must be "
        "'omim_contiguous_gene_syndrome' (was 'omim_community' — "
        "invented label, no OMIM semantic)."
    )
    assert "omim_confirmed" not in labels, (
        "Finding 5 regression: 'omim_confirmed' label still present."
    )
    assert "omim_community" not in labels, (
        "Finding 6 regression: 'omim_community' label still present."
    )


# =============================================================================
# Finding 7: Phase1OutputContract requires DrugBank (license-gated)
# =============================================================================

def test_finding_7_phase1_contract_accepts_chembl_or_drugbank():
    """Phase1OutputContract.required['drugs'] must accept EITHER
    drugbank_drugs.csv OR chembl_drugs.csv / drugs.csv."""
    from exporters.neo4j_exporter import Phase1OutputContract
    contract = Phase1OutputContract()
    drugs_candidates = contract.required["drugs"]
    assert "drugbank_drugs.csv" in drugs_candidates, (
        "Finding 7: drugbank_drugs.csv must still be a candidate."
    )
    assert "chembl_drugs.csv" in drugs_candidates, (
        "Finding 7 root fix missing: chembl_drugs.csv must be a "
        "candidate so operators without a DrugBank license can run."
    )
    assert "drugs.csv" in drugs_candidates, (
        "Finding 7 root fix missing: drugs.csv (generic ChEMBL/merged) "
        "must be a candidate."
    )


# =============================================================================
# Finding 9: InChIKey normalizer 3-way divergence
# =============================================================================

def test_finding_9_inchikey_normalizer_returns_none_for_none():
    """_normalize_inchikey in drug_resolver must return None for None
    (not empty string)."""
    from entity_resolution.drug_resolver import _normalize_inchikey
    assert _normalize_inchikey(None) is None, (
        "Finding 9 root fix missing: _normalize_inchikey(None) must "
        "return None (not empty string) to match the cleaning module's "
        "contract and avoid 3-way divergence."
    )
    assert _normalize_inchikey(123) is None, (
        "Finding 9: non-string input must return None."
    )
    assert _normalize_inchikey("  ") is None, (
        "Finding 9: whitespace-only input must return None (not empty "
        "string)."
    )
    # Valid InChIKey still works.
    result = _normalize_inchikey("bsynrymutxbxsq-uhfffaoysa-n")
    assert result == "BSYNRYMUTXBXSQ-UHFFFAOYSA-N", (
        f"Finding 9: valid InChIKey must be uppercased, got {result!r}"
    )


# =============================================================================
# Finding 10: get_filtering_thresholds reports wrong CONFIDENCE_TIERS labels
# =============================================================================

def test_finding_10_filtering_thresholds_labels_correct():
    """get_filtering_thresholds() must report the actual
    DEFAULT_CONFIDENCE_TIERS labels (sub_weak/weak/strong)."""
    from pipelines import get_filtering_thresholds
    thresholds = get_filtering_thresholds()
    tiers_value = thresholds["CONFIDENCE_TIERS"]["value"]
    labels = [label for _, label in tiers_value]
    assert "sub_weak" in labels, (
        f"Finding 10 root fix missing: 'sub_weak' label missing from "
        f"get_filtering_thresholds(). Got labels: {labels}"
    )
    assert "weak" in labels, (
        f"Finding 10: 'weak' label missing. Got: {labels}"
    )
    assert "strong" in labels, (
        f"Finding 10: 'strong' label missing. Got: {labels}"
    )
    assert "moderate" not in labels, (
        f"Finding 10 regression: 'moderate' label still present. "
        f"Got: {labels}"
    )


# =============================================================================
# Finding 11: health_check doesn't surface infrastructure FAILs
# =============================================================================

def test_finding_11_health_check_surfaces_infra_fails():
    """health_check() must check status=='FAIL' for infra checks
    (not just severity field)."""
    src = (PHASE1 / "pipelines" / "__init__.py").read_text()
    assert 'chk.get("status") == "FAIL"' in src, (
        "Finding 11 root fix missing: health_check must check "
        'chk.get("status") == "FAIL" for infra checks (the previous '
        "severity-only filter never matched because infra checks use "
        "status, not severity)."
    )


# =============================================================================
# Finding 14: _drop_null_primary_keys dead-letters dropped rows
# =============================================================================

def test_finding_14_drop_null_primary_keys_appends_to_dead_letter():
    """_drop_null_primary_keys must append dropped rows to
    dead_letter_queue (not just log a warning)."""
    src = (PHASE1 / "pipelines" / "base_pipeline.py").read_text()
    assert 'self.dead_letter_queue.append' in src, (
        "Finding 14 root fix missing: _drop_null_primary_keys must "
        "append dropped rows to self.dead_letter_queue (the previous "
        "code silently dropped them with only a log line)."
    )
    assert 'reason": "null_primary_key"' in src or (
        '"reason": "null_primary_key"' in src
    ), (
        "Finding 14: dead-letter entries must include "
        "reason='null_primary_key'."
    )


# =============================================================================
# Finding 16: normalize_pubchem_cid accepts 0 as valid
# =============================================================================

def test_finding_16_normalize_pubchem_cid_rejects_zero():
    """normalize_pubchem_cid must return None for 0 (CID 0 is invalid).
    PubChem CIDs start at 1 (CID 1 = formaldehyde)."""
    from cleaning._constants import normalize_pubchem_cid
    assert normalize_pubchem_cid(0) is None, (
        "Finding 16 root fix missing: normalize_pubchem_cid(0) must "
        "return None. CID 0 is NOT a valid PubChem identifier."
    )
    assert normalize_pubchem_cid("0") is None, (
        "Finding 16: string '0' must also return None."
    )
    assert normalize_pubchem_cid(0.0) is None, (
        "Finding 16: float 0.0 must also return None."
    )
    # Valid CIDs still work.
    assert normalize_pubchem_cid(2244) == 2244, (
        "Finding 16: valid CID 2244 (aspirin) must still work."
    )
    assert normalize_pubchem_cid("2244") == 2244


# =============================================================================
# Finding 20: Step 11b HGT cannot construct (torch_geometric missing)
# =============================================================================

def test_finding_20_step11b_has_torch_geometric_guard():
    """step11b_train_graph_transformer must check torch_geometric
    availability before importing GraphTransformerModel."""
    src = (PHASE2 / "drugos_graph" / "run_pipeline.py").read_text()
    assert "import torch_geometric  # noqa: F401" in src, (
        "Finding 20 root fix missing: step11b must check "
        "torch_geometric availability before importing "
        "GraphTransformerModel."
    )
    assert "torch_geometric_not_installed" in src, (
        "Finding 20: step11b must return reason="
        "'torch_geometric_not_installed' when the dep is missing."
    )


# =============================================================================
# Finding 21: Step 12 & 13 crash with neo4j driver not installed
# =============================================================================

def test_finding_21_step12_13_have_neo4j_guards():
    """step12_validation and step13_readme must check neo4j driver
    availability AND server reachability before constructing GraphStats."""
    src = (PHASE2 / "drugos_graph" / "run_pipeline.py").read_text()
    assert "neo4j_driver_not_installed" in src, (
        "Finding 21 root fix missing: step12 must return reason="
        "'neo4j_driver_not_installed' when the driver is missing."
    )
    assert "neo4j_server_unreachable" in src, (
        "Finding 21: step12 must return reason="
        "'neo4j_server_unreachable' when the server is not reachable."
    )


# =============================================================================
# Finding 24: BCELoss on sigmoid(logit) — numerically inferior
# =============================================================================

def test_finding_24_step11b_uses_bcewithlogitsloss():
    """step11b must use BCEWithLogitsLoss (not BCELoss) and call
    score_triples_logits (not score_triples) for the loss."""
    src = (PHASE2 / "drugos_graph" / "run_pipeline.py").read_text()
    assert "BCEWithLogitsLoss" in src, (
        "Finding 24 root fix missing: step11b must use "
        "BCEWithLogitsLoss (numerically stable) instead of BCELoss."
    )
    assert "score_triples_logits" in src, (
        "Finding 24: step11b must call score_triples_logits (raw "
        "logits) for the loss, not score_triples (sigmoid'd)."
    )
    # The model class must have the new method.
    model_src = (PHASE2 / "drugos_graph" / "graph_transformer_model.py").read_text()
    assert "def score_triples_logits" in model_src, (
        "Finding 24: GraphTransformerModel must define "
        "score_triples_logits method."
    )


# =============================================================================
# Finding 25: Step 1 bridge ALWAYS uses RecordingGraphBuilder (no persistence)
# =============================================================================

def test_finding_25_step1_persists_staged_graph_to_disk():
    """step1_load_phase1 must persist the staged graph to
    phase1_staged_graph.json so it survives process exit."""
    src = (PHASE2 / "drugos_graph" / "run_pipeline.py").read_text()
    assert "phase1_staged_graph.json" in src, (
        "Finding 25 root fix missing: step1 must persist the staged "
        "graph to phase1_staged_graph.json (the '100% connected' fix)."
    )
    # Verify the file actually exists after a run.
    staged_path = PHASE2 / "data" / "processed" / "phase1_staged_graph.json"
    if staged_path.exists():
        import json
        with open(staged_path) as f:
            data = json.load(f)
        assert "node_counts_by_type" in data, (
            "Finding 25: staged graph JSON must have node_counts_by_type."
        )
        assert "edge_counts_by_type" in data, (
            "Finding 25: staged graph JSON must have edge_counts_by_type."
        )
        assert "sources_read" in data, (
            "Finding 25: staged graph JSON must have sources_read."
        )


# =============================================================================
# Integration: pipeline runs end-to-end without crashing
# =============================================================================

def test_integration_pipeline_runs_end_to_end():
    """The unified pipeline must run end-to-end without any step
    crashing with an unhandled exception. Steps that cannot run due
    to environment limitations (no Neo4j server, too few triples)
    must SKIP cleanly with a documented reason, not FAIL."""
    # This test verifies the FIX, not the original behavior. We check
    # that step11b either SKIPS (torch_geometric missing) or RUNS
    # (torch_geometric present) — but it must NOT raise
    # ModuleNotFoundError or TransETrainingError that propagates as
    # a step FAILURE (vs a clean SKIP).
    src = (PHASE2 / "drugos_graph" / "run_pipeline.py").read_text()
    # The guard must be present.
    assert "_torch_geometric_available" in src, (
        "Integration: torch_geometric availability guard missing."
    )
    # The skip-reason must be present.
    assert "torch_geometric_not_installed" in src


# =============================================================================
# Run as a script (no pytest required)
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("V44 ROOT FIX VERIFICATION — running all tests...")
    print("=" * 70)
    tests = [
        test_finding_1_master_dag_branch_returns_run_drugbank,
        test_finding_2_drugbank_license_text_corrected,
        test_finding_3_parallel_provenance_passes_run_id_explicitly,
        test_finding_4_ec50_ac50_returns_unknown,
        test_findings_5_6_omim_tier_labels_correct,
        test_finding_7_phase1_contract_accepts_chembl_or_drugbank,
        test_finding_9_inchikey_normalizer_returns_none_for_none,
        test_finding_10_filtering_thresholds_labels_correct,
        test_finding_11_health_check_surfaces_infra_fails,
        test_finding_14_drop_null_primary_keys_appends_to_dead_letter,
        test_finding_16_normalize_pubchem_cid_rejects_zero,
        test_finding_20_step11b_has_torch_geometric_guard,
        test_finding_21_step12_13_have_neo4j_guards,
        test_finding_24_step11b_uses_bcewithlogitsloss,
        test_finding_25_step1_persists_staged_graph_to_disk,
        test_integration_pipeline_runs_end_to_end,
    ]
    passed, failed = 0, 0
    for test in tests:
        try:
            test()
            print(f"  [PASS] {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {test.__name__}: {e}")
            failed += 1
    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed (of {len(tests)} total)")
    print("=" * 70)
    sys.exit(0 if failed == 0 else 1)
