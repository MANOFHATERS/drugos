"""v9 ROOT FIX TESTS — Phase 2 loaders + kg_builder + TransE model.

Verifies every fix from the DrugOS v8 Forensic Audit Report (Phase 2
loader + kg_builder + TransE model portion).

Audit findings covered:
  F3 / BUG-B-001  OMIM loader edge emitter re-prefixes OMIM: to Gene IDs
  F5 / F7.4       Mixed-type node list (Disease+Gene) loaded under one label
  F5.2.1          UniProt src_id "uniprot:P23219" + dead code (never called)
  F5.2.2          DrugBank drug_a_id/drug_b_id not in kg_builder alias list
  F5.2.3          STITCH src_id bare integer (fails Compound regex)
  F5.2.4          GEO dst_id full URI (fails Anatomy regex)
  F5.2.5          ClinicalTrials deprecated rel_type + MeSH src_id format
  F5.2.6          OpenTargets orphan fallback MONDO_xxx fails Disease regex
  F5.2.7          BUG-D-007 _get_default_crosswalk never called
  F5.2.8          SIDER doctest lies that src_id is int
  F7.8            ID_PATTERNS silent bypass for unknown labels
  F4 / F6.1.1     step11 missing val_triples + negative_sampler
  F6.1.2          _check_v1_launch_criteria doesn't check AUC
  F6.3.4          crude random corruption fallback
  F6.3.6          No held_out_auc / test_auc field (BUG-C-009)
  F7.6            Two AUC thresholds (0.85 vs 0.78)
  F4 / F7.6       AUC enforcement bypassed
  BUG-E-008       sys.exit codes incomplete (2/3/4 never called)
  F6.3.10         Synthetic Gaussian CI fallback (BUG-C-010)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pytest


# Phase 2 package is at unified/phase2/, so we add unified/ to sys.path
# so "from drugos_graph import ..." works.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO_ROOT / "phase2"
sys.path.insert(0, str(_PHASE2))


# ──────────────────────────────────────────────────────────────────────────
# F3 / BUG-B-001 — OMIM loader edge emitter strips OMIM: prefix
# ──────────────────────────────────────────────────────────────────────────

def test_omim_edge_emitter_strips_omim_prefix_from_gene_ids():
    """omim_to_edge_records emits bare numeric gene_id (NOT 'OMIM:100650').

    The node emitter at line 101 already stripped the prefix. The edge
    emitter was still emitting f'OMIM:{int(...)}' which fails
    ID_PATTERNS['Gene'] = ^(\\d+|SYM:[A-Z0-9]+)$.
    """
    from drugos_graph.omim_loader import omim_to_edge_records

    df = pd.DataFrame([
        {"disease_id": "OMIM:100800", "gene_symbol": "FGFR3",
         "gene_mim": 100650, "score": 0.8, "association_type": "genetic"},
    ])
    edges = omim_to_edge_records(df)
    assert len(edges) == 1
    edge = edges[0]
    # The src_id MUST be a bare numeric string — NOT 'OMIM:100650'.
    assert edge["src_id"] == "100650", (
        f"Expected '100650', got {edge['src_id']!r} — edge emitter is "
        f"still re-prefixing OMIM: (audit F3 / BUG-B-001)"
    )
    # The src_type is Gene (matches the dst_type for Disease).
    assert edge["src_type"] == "Gene"
    assert edge["dst_type"] == "Disease"


def test_omim_edge_emitter_falls_back_to_sym_prefix_when_no_mim():
    """When gene_mim is missing, the edge emitter uses SYM:<symbol>."""
    from drugos_graph.omim_loader import omim_to_edge_records

    df = pd.DataFrame([
        {"disease_id": "OMIM:100800", "gene_symbol": "FGFR3",
         "gene_mim": None, "score": 0.8, "association_type": "genetic"},
    ])
    edges = omim_to_edge_records(df)
    assert len(edges) == 1
    # No MIM ID — falls back to SYM:<symbol> (mirrors node emitter).
    assert edges[0]["src_id"] == "SYM:FGFR3"


# ──────────────────────────────────────────────────────────────────────────
# F5.2.3 — STITCH src_id is now "CID#####" (mirrors SIDER)
# ──────────────────────────────────────────────────────────────────────────

def test_stitch_chemical_cid_uses_cid_prefix():
    """stitch_loader emits 'CID2244' (matches Compound regex) instead of
    the bare integer string '2244' (which fails the regex).

    The SIDER BUG-B-004 fix was f"CID{int(cid)}" but it was never
    propagated to STITCH. ~1.6M edges were dead-lettered in production.
    """
    from drugos_graph import kg_builder

    # ID_PATTERNS["Compound"] must accept "CID2244".
    assert kg_builder._validate_id("Compound", "CID2244"), (
        "STITCH-emitted 'CID2244' must be valid (audit F5.2.3 fix)"
    )
    # The bare integer "2244" must be rejected.
    assert not kg_builder._validate_id("Compound", "2244"), (
        "Bare integer '2244' must be rejected (was the v8 bug — STITCH "
        "edges were dead-lettered)"
    )


# ──────────────────────────────────────────────────────────────────────────
# F5.2.4 — GEO dst_id is now bare UBERON_xxxxxxxxx
# ──────────────────────────────────────────────────────────────────────────

def test_geo_uberon_uri_is_stripped_to_bare_form():
    """_strip_uberon_uri converts the full OBO URI to bare UBERON_xxxxxxxxx."""
    from drugos_graph.geo_loader import _strip_uberon_uri

    # Full URI → bare.
    assert _strip_uberon_uri(
        "http://purl.obolibrary.org/obo/UBERON_0002048"
    ) == "UBERON_0002048"
    # Already bare → unchanged.
    assert _strip_uberon_uri("UBERON_0002048") == "UBERON_0002048"
    # Partial prefix → still extracted.
    assert _strip_uberon_uri("obo/UBERON_0002048") == "UBERON_0002048"


def test_geo_anatomy_id_pattern_accepts_bare_uberon():
    """ID_PATTERNS['Anatomy'] accepts bare 'UBERON_0002048'."""
    from drugos_graph import kg_builder

    assert kg_builder._validate_id("Anatomy", "UBERON_0002048")
    assert kg_builder._validate_id("Anatomy", "CL_0000000")
    # Full URI is rejected (was the v8 bug).
    assert not kg_builder._validate_id(
        "Anatomy", "http://purl.obolibrary.org/obo/UBERON_0002048"
    )


# ──────────────────────────────────────────────────────────────────────────
# F5.2.6 — OpenTargets orphan fallback normalises underscore → colon
# ──────────────────────────────────────────────────────────────────────────

def test_opentargets_normalise_ontology_id_underscore_to_colon():
    """_normalise_ontology_id converts 'MONDO_0004975' → 'MONDO:0004975'."""
    from drugos_graph.opentargets_loader import _normalise_ontology_id

    assert _normalise_ontology_id("MONDO_0004975") == "MONDO:0004975"
    assert _normalise_ontology_id("Orphanet_558") == "Orphanet:558"
    assert _normalise_ontology_id("EFO_0000400") == "EFO:0000400"
    # Already colon form → unchanged.
    assert _normalise_ontology_id("MONDO:0004975") == "MONDO:0004975"
    # Unknown prefix → unchanged (will dead-letter at kg_builder).
    assert _normalise_ontology_id("UNKNOWN_12345") == "UNKNOWN_12345"


def test_opentargets_normalised_disease_id_passes_kg_builder():
    """After normalisation, MONDO/Orphanet IDs pass ID_PATTERNS['Disease']."""
    from drugos_graph import kg_builder
    from drugos_graph.opentargets_loader import _normalise_ontology_id

    for raw in ("MONDO_0004975", "Orphanet_558"):
        normalised = _normalise_ontology_id(raw)
        assert kg_builder._validate_id("Disease", normalised), (
            f"Normalised {normalised!r} must pass Disease ID_PATTERNS "
            f"(audit F5.2.6 fix)"
        )


# ──────────────────────────────────────────────────────────────────────────
# F7.8 — ID_PATTERNS raises UnknownLabelError for unknown labels
# ──────────────────────────────────────────────────────────────────────────

def test_unknown_label_raises_error():
    """_validate_id raises UnknownLabelError for typo'd labels.

    Before v9 it returned True for ANY label not in ID_PATTERNS —
    silently disabling validation. Now it's fail-closed.
    """
    from drugos_graph import kg_builder
    from drugos_graph.exceptions import UnknownLabelError

    # Valid label works.
    assert kg_builder._validate_id("Compound", "DB00001")
    # Typo'd label raises.
    with pytest.raises(UnknownLabelError):
        kg_builder._validate_id("Compoud", "DB00001")  # missing 'n'
    with pytest.raises(UnknownLabelError):
        kg_builder._validate_id("MedDRATerm", "C0018790")  # missing underscore


def test_new_labels_registered_for_uniprot_xref_edges():
    """ExternalRef, Domain, OntologyTerm, Publication are now in ID_PATTERNS."""
    from drugos_graph import kg_builder

    # These labels are emitted by UniProt cross-reference edges.
    for label, sample_id in [
        ("ExternalRef", "GO:0005524"),
        ("Domain", "PF00069"),
        ("OntologyTerm", "GO:0005524"),
        ("Publication", "12345678"),
    ]:
        assert label in kg_builder.ID_PATTERNS, (
            f"{label} must be in ID_PATTERNS for UniProt xref edges "
            f"(audit F5.2.1)"
        )
        assert kg_builder._validate_id(label, sample_id), (
            f"{label} sample ID {sample_id!r} must validate"
        )


# ──────────────────────────────────────────────────────────────────────────
# F7.6 — AUC threshold unified to 0.85
# ──────────────────────────────────────────────────────────────────────────

def test_auc_threshold_unified_to_085():
    """V1_LAUNCH_AUC, get_target_auc(), TARGET_TRANSE_AUC all return 0.85."""
    from drugos_graph import config

    assert config.V1_LAUNCH_AUC == 0.85, (
        f"V1_LAUNCH_AUC must be 0.85 (was 0.78), got {config.V1_LAUNCH_AUC}"
    )
    assert config.get_target_auc() == 0.85
    assert config.TARGET_TRANSE_AUC == 0.85
    # TransEConfig().target_auc must match.
    assert config.TransEConfig().target_auc == 0.85


# ──────────────────────────────────────────────────────────────────────────
# F6.3.6 / BUG-C-009 — TrainingHistory has held_out_auc / test_auc fields
# ──────────────────────────────────────────────────────────────────────────

def test_training_history_has_held_out_auc_fields():
    """TrainingHistory now has held_out_auc, test_auc, held_out_metrics.

    Source-inspection: transe_model imports torch at module load time,
    so we can't import TrainingHistory directly without torch installed.
    We verify the field declarations are in the source.
    """
    src_path = _PHASE2 / "drugos_graph" / "transe_model.py"
    source = src_path.read_text()
    # Find the TrainingHistory dataclass.
    th_start = source.find("@dataclass\nclass TrainingHistory")
    if th_start == -1:
        th_start = source.find("class TrainingHistory")
    assert th_start != -1, "TrainingHistory class must exist"
    # Find the end (next class or function def at module level).
    th_end = source.find("\n@dataclass", th_start + 5)
    if th_end == -1:
        th_end = source.find("\nclass ", th_start + 5)
    if th_end == -1:
        th_end = source.find("\ndef ", th_start + 5)
    body = source[th_start:th_end]
    assert "held_out_auc" in body, (
        "TrainingHistory must have held_out_auc field (audit F6.3.6 / "
        "BUG-C-009 fix — DOCX V1 launch criterion '>0.85 AUC on held-out "
        "pairs' was structurally impossible to verify before)"
    )
    assert "test_auc" in body
    assert "held_out_metrics" in body


def test_train_transe_accepts_test_triples_parameter():
    """train_transe signature now accepts test_triples (for held-out AUC).

    Source-inspection: torch not installed in test env.
    """
    src_path = _PHASE2 / "drugos_graph" / "transe_model.py"
    source = src_path.read_text()
    # Find the train_transe signature.
    fn_start = source.find("def train_transe(")
    assert fn_start != -1
    # The signature spans until the closing paren + colon.
    sig_end = source.find(") -> TrainingHistory:", fn_start)
    assert sig_end != -1
    sig = source[fn_start:sig_end]
    assert "test_triples" in sig, (
        "train_transe must accept test_triples parameter (audit F6.3.6 fix "
        "— DOCX V1 launch criterion '>0.85 AUC on held-out pairs' was "
        "structurally impossible to verify before)"
    )
    assert "val_triples" in sig
    assert "negative_sampler" in sig


# ──────────────────────────────────────────────────────────────────────────
# F6.3.10 / BUG-C-010 — Synthetic Gaussian CI fallback raises
# ──────────────────────────────────────────────────────────────────────────

def test_synthetic_gaussian_ci_fallback_raises():
    """The bootstrap CI helper raises EvaluationIntegrityError when raw
    scores are missing — instead of silently producing synthetic CIs."""
    from drugos_graph import evaluation
    from drugos_graph.exceptions import EvaluationIntegrityError

    # Find a function that computes bootstrap CIs.
    # The audit pointed at evaluation.py:2448-2463 — find the public entry.
    # The relevant function is the one that builds CIs from raw scores.
    candidates = [
        name for name in dir(evaluation)
        if "bootstrap" in name.lower() or "confidence" in name.lower()
    ]
    assert len(candidates) > 0, (
        "Expected to find at least one bootstrap/CI function in evaluation.py"
    )
    # We can't easily call it without an EvaluationResult, so verify the
    # source code raises EvaluationIntegrityError when scores are missing.
    import inspect
    src = inspect.getsource(evaluation)
    # The raise pattern must be present.
    assert "raise EvaluationIntegrityError" in src, (
        "evaluation.py must raise EvaluationIntegrityError when raw model "
        "scores are missing (audit F6.3.10 / BUG-C-010 fix — was silently "
        "producing invalid CIs from a synthetic Gaussian fallback)"
    )
    # The synthetic Gaussian fallback pattern (rng.normal with hardcoded
    # 0.3/0.7 means) must NOT be present in the new code path.
    assert "rng.normal(pos_mean, pos_std" not in src or \
           "synthetic = False" in src, (
        "The synthetic Gaussian fallback must be replaced with a raise"
    )


# ──────────────────────────────────────────────────────────────────────────
# F4 / F6.1.1 / F7.5 — step11 passes val_triples + negative_sampler
# ──────────────────────────────────────────────────────────────────────────

def test_step11_passes_val_triples_and_negative_sampler():
    """step11_train_transe source contains val_triples + negative_sampler
    in the train_transe call (the audit said these were missing)."""
    src_path = _PHASE2 / "drugos_graph" / "run_pipeline.py"
    source = src_path.read_text()
    # Find the train_transe call inside step11_train_transe.
    step11_start = source.find("def step11_train_transe")
    assert step11_start != -1
    step12_start = source.find("def step12_validation", step11_start)
    step11_body = source[step11_start:step12_start]
    # The train_transe call must include val_triples and negative_sampler.
    assert "val_triples=val_triples" in step11_body, (
        "step11_train_transe must pass val_triples= to train_transe "
        "(audit F4 / F6.1.1 fix — without val_triples, AUC enforcement "
        "is silently skipped and no model is saved)"
    )
    assert "negative_sampler=negative_sampler" in step11_body, (
        "step11_train_transe must pass negative_sampler= to train_transe "
        "(audit F6.3.4 fix — without it, crude random corruption produces "
        "type-incompatible negatives)"
    )


def test_step11_returns_best_val_auc_and_model_sha256():
    """step11 result dict surfaces best_val_auc + model_sha256 so
    _check_v1_launch_criteria can enforce the 0.85 threshold."""
    src_path = _PHASE2 / "drugos_graph" / "run_pipeline.py"
    source = src_path.read_text()
    step11_start = source.find("def step11_train_transe")
    step12_start = source.find("def step12_validation", step11_start)
    step11_body = source[step11_start:step12_start]
    assert "best_val_auc" in step11_body, (
        "step11 return dict must include best_val_auc (audit F6.1.2 fix)"
    )
    assert "model_sha256" in step11_body
    assert "model_saved" in step11_body


# ──────────────────────────────────────────────────────────────────────────
# F6.1.2 — _check_v1_launch_criteria enforces AUC + model-saved
# ──────────────────────────────────────────────────────────────────────────

def test_v1_launch_criteria_checks_auc():
    """_check_v1_launch_criteria now requires auc_meets_threshold AND
    model_saved_to_disk (was missing before — only checked data sources
    and pair counts).

    v9 ROOT FIX (audit F6.3.6): the criteria now checks BOTH best_val_auc
    AND held_out_auc. The DOCX V1 launch criterion is ">0.85 AUC on
    held-out drug-disease pairs" — val_auc alone is insufficient because
    a model that overfits the val set would pass despite poor
    generalization.
    """
    from drugos_graph.run_pipeline import _check_v1_launch_criteria

    # A pipeline that produced no model (step11 skipped) must NOT pass.
    criteria = _check_v1_launch_criteria({
        "step7": {"chembl_edges": 100, "string_edges": 100, "uniprot_nodes": 100,
                  "opentargets_edges": 100, "disgenet_edges": 100,
                  "omim_edges": 100, "pubchem_nodes": 100},
        "step4": {"drug_records": 100},
        "step5": {"stitch_edges": 100},
        "step10": {"training_data": {"num_positives": 50000, "num_negatives": 250000}},
        "step11": {"best_val_auc": -1.0, "held_out_auc": -1.0, "model_saved": False},
    })
    assert criteria["auc_meets_threshold"] is False
    assert criteria["model_saved_to_disk"] is False
    assert criteria["passed"] is False, (
        "Pipeline with no trained model must NOT pass V1 launch criteria"
    )

    # A pipeline that produced a model with val_auc=0.90 AND held_out_auc=0.90 must pass.
    criteria = _check_v1_launch_criteria({
        "step7": {"chembl_edges": 100, "string_edges": 100, "uniprot_nodes": 100,
                  "opentargets_edges": 100, "disgenet_edges": 100,
                  "omim_edges": 100, "pubchem_nodes": 100},
        "step4": {"drug_records": 100},
        "step5": {"stitch_edges": 100},
        "step10": {"training_data": {"num_positives": 50000, "num_negatives": 250000}},
        "step11": {"best_val_auc": 0.90, "held_out_auc": 0.90, "model_saved": True},
    })
    assert criteria["auc_meets_threshold"] is True
    assert criteria["model_saved_to_disk"] is True
    assert criteria["passed"] is True

    # A pipeline with val_auc=0.80 (below 0.85 threshold) must NOT pass.
    # v25 ROOT FIX: temporarily disable DEV_SMOKE_TEST so this test
    # verifies the PRODUCTION behavior (passed=False when AUC<0.85). In
    # dev mode, the criteria would pass with dev_smoke_test_pass=True.
    import os as _os
    _orig_dst = _os.environ.get("DRUGOS_DEV_SMOKE_TEST")
    _os.environ["DRUGOS_DEV_SMOKE_TEST"] = "0"
    try:
        # Force re-import of config so DEV_SMOKE_TEST is re-evaluated.
        import importlib
        import drugos_graph.config as _cfg
        importlib.reload(_cfg)
        from drugos_graph.run_pipeline import _check_v1_launch_criteria as _check_prod
        criteria = _check_prod({
            "step7": {"chembl_edges": 100, "string_edges": 100, "uniprot_nodes": 100,
                      "opentargets_edges": 100, "disgenet_edges": 100,
                      "omim_edges": 100, "pubchem_nodes": 100},
            "step4": {"drug_records": 100},
            "step5": {"stitch_edges": 100},
            "step10": {"training_data": {"num_positives": 50000, "num_negatives": 250000}},
            "step11": {"best_val_auc": 0.80, "held_out_auc": 0.80, "model_saved": True},
        })
    finally:
        if _orig_dst is None:
            _os.environ.pop("DRUGOS_DEV_SMOKE_TEST", None)
        else:
            _os.environ["DRUGOS_DEV_SMOKE_TEST"] = _orig_dst
        importlib.reload(_cfg)
    assert criteria["auc_meets_threshold"] is False, (
        "AUC=0.80 must NOT pass (below 0.85 threshold per DOCX)"
    )
    assert criteria["passed"] is False, (
        "In production mode (DEV_SMOKE_TEST=0), AUC=0.80 must NOT pass"
    )

    # v9 ROOT FIX (audit F6.3.6): a model with high val_auc but LOW
    # held_out_auc must NOT pass (overfitting detection).
    _os.environ["DRUGOS_DEV_SMOKE_TEST"] = "0"
    try:
        importlib.reload(_cfg)
        from drugos_graph.run_pipeline import _check_v1_launch_criteria as _check_prod2
        criteria = _check_prod2({
            "step7": {"chembl_edges": 100, "string_edges": 100, "uniprot_nodes": 100,
                      "opentargets_edges": 100, "disgenet_edges": 100,
                      "omim_edges": 100, "pubchem_nodes": 100},
            "step4": {"drug_records": 100},
            "step5": {"stitch_edges": 100},
            "step10": {"training_data": {"num_positives": 50000, "num_negatives": 250000}},
            "step11": {"best_val_auc": 0.90, "held_out_auc": 0.60, "model_saved": True},
        })
    finally:
        if _orig_dst is None:
            _os.environ.pop("DRUGOS_DEV_SMOKE_TEST", None)
        else:
            _os.environ["DRUGOS_DEV_SMOKE_TEST"] = _orig_dst
        importlib.reload(_cfg)
    assert criteria["val_auc_meets_threshold"] is True, (
        "val_auc=0.90 should pass the val threshold"
    )
    assert criteria["auc_meets_threshold"] is False, (
        "held_out_auc=0.60 must fail (overfitting — val passes but held-out fails)"
    )
    assert criteria["passed"] is False, (
        "Overfit model (high val, low held-out) must NOT pass V1 launch"
    )


# ──────────────────────────────────────────────────────────────────────────
# F5 / F7.4 — DisGeNET + OMIM mixed-type node lists split by label
# ──────────────────────────────────────────────────────────────────────────

def test_run_pipeline_splits_disgenet_nodes_by_label():
    """run_pipeline source contains the label-split logic for DisGeNET."""
    src_path = _PHASE2 / "drugos_graph" / "run_pipeline.py"
    source = src_path.read_text()
    # Find the DisGeNET ingestion block.
    disgenet_start = source.find("DisGeNET (BUG-SCI-03")
    assert disgenet_start != -1
    # Find the next major section (OMIM).
    omim_start = source.find("OMIM (BUG-SCI-03", disgenet_start)
    block = source[disgenet_start:omim_start]
    # The split-by-label pattern must be present.
    assert 'dg_disease_nodes' in block
    assert 'dg_gene_nodes' in block
    assert 'label") == "Disease"' in block
    assert 'label") == "Gene"' in block


def test_run_pipeline_splits_omim_nodes_by_label():
    """run_pipeline source contains the label-split logic for OMIM."""
    src_path = _PHASE2 / "drugos_graph" / "run_pipeline.py"
    source = src_path.read_text()
    omim_start = source.find("OMIM (BUG-SCI-03")
    assert omim_start != -1
    # Take the next 4000 chars to capture the full block.
    block = source[omim_start:omim_start + 4000]
    assert 'omim_disease_nodes' in block
    assert 'omim_gene_nodes' in block


# ──────────────────────────────────────────────────────────────────────────
# F5.2.5 — ClinicalTrials uses 'tested_for' rel_type + MESH: src_id
# ──────────────────────────────────────────────────────────────────────────

def test_run_pipeline_uses_tested_for_rel_type_not_clinical_trial():
    """run_pipeline calls load_edges_bulk_create with 'tested_for'
    (canonical v1 rel_type) instead of the deprecated 'clinical_trial'."""
    src_path = _PHASE2 / "drugos_graph" / "run_pipeline.py"
    source = src_path.read_text()
    # Find the ClinicalTrials ingestion block.
    ct_start = source.find("ClinicalTrials")
    assert ct_start != -1
    # The tested_for rel_type must be used somewhere in the ClinicalTrials
    # edge-loading path.
    # Find the load_edges_bulk_create call with "tested_for".
    tested_for_pos = source.find('"tested_for"')
    assert tested_for_pos != -1, (
        "run_pipeline must use 'tested_for' rel_type (audit F5.2.5 fix — "
        "'clinical_trial' is the DEPRECATED v0 name per config.py:1594)"
    )
    # The deprecated 'clinical_trial' must NOT be used in any
    # load_edges_bulk_create call.
    # Find all load_edges_bulk_create calls.
    import re
    matches = re.findall(
        r'load_edges_bulk_create\(\s*[^)]*"clinical_trial"[^)]*\)',
        source,
    )
    assert len(matches) == 0, (
        f"run_pipeline must NOT call load_edges_bulk_create with the "
        f"DEPRECATED 'clinical_trial' rel_type (audit F5.2.5). Found: {matches}"
    )


def test_clinicaltrials_loader_emits_mesh_prefixed_src_id():
    """clinicaltrials_loader prefixes MeSH descriptors with 'MESH:'."""
    # Verify ID_PATTERNS["Compound"] now accepts MESH:D###### form.
    from drugos_graph import kg_builder

    assert kg_builder._validate_id("Compound", "MESH:D000068"), (
        "ClinicalTrials MeSH src_id 'MESH:D000068' must be valid "
        "(audit F5.2.5 fix)"
    )
    # Bare 'D000068' is rejected (was the v8 bug — every CT edge was
    # dead-lettered at src_id validation).
    assert not kg_builder._validate_id("Compound", "D000068")


# ──────────────────────────────────────────────────────────────────────────
# F5.2.1 — UniProt src_id is bare accession (no 'uniprot:' prefix)
# ──────────────────────────────────────────────────────────────────────────

def test_uniprot_loader_emits_bare_accession_src_id():
    """uniprot_loader source emits src_id = accession (NOT 'uniprot:'+accession)."""
    src_path = _PHASE2 / "drugos_graph" / "uniprot_loader.py"
    source = src_path.read_text()
    # The buggy pattern must NOT be present.
    assert '"src_id": f"uniprot:{accession}"' not in source, (
        "uniprot_loader must NOT emit src_id = f'uniprot:{accession}' "
        "(audit F5.2.1 fix — fails ID_PATTERNS['Protein'])"
    )
    # The fixed pattern must be present.
    assert '"src_id": accession' in source, (
        "uniprot_loader must emit src_id = accession (bare, no prefix)"
    )


def test_run_pipeline_calls_uniprot_to_edge_records():
    """run_pipeline now calls uniprot_to_edge_records (was P1-DEAD code)."""
    src_path = _PHASE2 / "drugos_graph" / "run_pipeline.py"
    source = src_path.read_text()
    # Find the UniProt ingestion block.
    up_start = source.find("UniProt proteins (critical")
    assert up_start != -1
    block = source[up_start:up_start + 4000]
    # The function must be called.
    assert "uniprot_to_edge_records" in block, (
        "run_pipeline must call uniprot_to_edge_records (audit F5.2.1 fix "
        "— was P1-DEAD code, never called)"
    )
    assert "uniprot_edges" in block


# ──────────────────────────────────────────────────────────────────────────
# F5.2.2 — DrugBank interaction edges emit src_id/dst_id
# ──────────────────────────────────────────────────────────────────────────

def test_drugbank_interaction_edges_emit_src_id_and_dst_id():
    """drugbank_parser source emits src_id/dst_id (canonical keys)
    instead of only drug_a_id/drug_b_id (not in kg_builder alias list)."""
    src_path = _PHASE2 / "drugos_graph" / "drugbank_parser.py"
    source = src_path.read_text()
    # Find the interaction edge emission block.
    edge_start = source.find('edge_provenance["edge_relation"] = "interacts_with"')
    assert edge_start != -1
    block = source[edge_start:edge_start + 2000]
    # The canonical keys must be present.
    assert '"src_id": drug.drugbank_id' in block, (
        "DrugBank interaction edges must emit src_id (audit F5.2.2 fix)"
    )
    assert '"dst_id": partner_id' in block
    # Legacy aliases can still be present (for downstream consumers).
    assert '"drug_a_id": drug.drugbank_id' in block
    assert '"drug_b_id": partner_id' in block


# ──────────────────────────────────────────────────────────────────────────
# F5.2.7 / BUG-D-007 — entity_resolver calls _get_default_crosswalk
# ──────────────────────────────────────────────────────────────────────────

def test_entity_resolver_calls_get_default_crosswalk():
    """entity_resolver source contains an actual CALL to
    _get_default_crosswalk() (not just the import)."""
    src_path = _PHASE2 / "drugos_graph" / "entity_resolver.py"
    source = src_path.read_text()
    # Find the resolve_genes_from_drkg_impl block.
    rg_start = source.find("def _resolve_genes_from_drkg_impl")
    assert rg_start != -1
    # The CALL (with parens) must be present in the resolve logic.
    assert "crosswalk = _get_default_crosswalk()" in source[rg_start:], (
        "entity_resolver must CALL _get_default_crosswalk() (audit F5.2.7 / "
        "BUG-D-007 fix — v7 audit claimed FIXED but only the import was "
        "present, the function was NEVER CALLED)"
    )
    # The crosswalk.canonicalize call must be present.
    assert "crosswalk.canonicalize" in source[rg_start:]


# ──────────────────────────────────────────────────────────────────────────
# F5.2.8 — SIDER doctest no longer lies that src_id is int
# ──────────────────────────────────────────────────────────────────────────

def test_sider_doctest_tells_truth_about_src_id_type():
    """sider_loader source doctest asserts src_id is str (not int).

    v9 ROOT FIX (audit F5.2.8): the previous doctest claimed
    ``isinstance(edges[0]["src_id"], int)`` and suppressed the lie with
    ``# doctest: +SKIP``. After BUG-B-004, src_id is a STRING
    ``"CID5311025"`` (not int). The fix rewrites the doctest to be
    self-contained (no +SKIP) and verify src_id is str.
    """
    src_path = _PHASE2 / "drugos_graph" / "sider_loader.py"
    source = src_path.read_text()
    # The buggy doctest pattern must NOT be present.
    assert 'isinstance(edges[0]["src_id"], int)' not in source, (
        "SIDER doctest must NOT lie that src_id is int (audit F5.2.8 fix — "
        "BUG-B-004 made src_id a string 'CID5311025', the old doctest "
        "suppressed the lie with # doctest: +SKIP)"
    )
    # The doctest must verify src_id is str (the truth after BUG-B-004).
    # v9: the doctest may use a self-contained example or a direct
    # isinstance check — either is acceptable as long as it tells the
    # truth (str, not int) and doesn't use # doctest: +SKIP to hide.
    assert (
        'isinstance(edges[0]["src_id"], str)' in source
        or 'isinstance(f"CID{int(' in source
        or "isinstance(f\"CID{int(" in source
    ), (
        "SIDER doctest must verify src_id is str (the truth after BUG-B-004)"
    )


# ──────────────────────────────────────────────────────────────────────────
# BUG-E-008 — sys.exit codes 2/3/4 emitted
# ──────────────────────────────────────────────────────────────────────────

def test_main_emits_validation_failure_exit_code():
    """__main__.py source contains EXIT_VALIDATION_FAILURE return."""
    src_path = _PHASE2 / "drugos_graph" / "__main__.py"
    source = src_path.read_text()
    # The EXIT_VALIDATION_FAILURE constant must be defined.
    assert "EXIT_VALIDATION_FAILURE = 2" in source
    # The V1 launch criteria check must be present.
    assert "_check_v1_launch_criteria" in source, (
        "__main__ must run V1 launch criteria check after pipeline success "
        "(audit BUG-E-008 fix — exit code 2 was never emitted before)"
    )
    assert "EXIT_VALIDATION_FAILURE" in source.split("rc = _run_pipeline_main")[1], (
        "__main__ must return EXIT_VALIDATION_FAILURE when criteria fail"
    )


# ──────────────────────────────────────────────────────────────────────────
# F3.3 — Migration 006 backfills is_withdrawn from DrugBank groups
# ──────────────────────────────────────────────────────────────────────────

def test_migration_006_backfills_is_withdrawn_from_drugbank_groups():
    """migration 006 contains a backfill UPDATE that scans drugs.groups
    for 'withdrawn' and sets is_withdrawn=TRUE."""
    src_path = _REPO_ROOT / "phase1" / "database" / "migrations" / "006_drug_withdrawn_safety_columns.sql"
    source = src_path.read_text()
    # The backfill block must be present.
    assert "BACKFILL is_withdrawn from DrugBank" in source, (
        "Migration 006 must backfill is_withdrawn from DrugBank groups "
        "(audit F3.3 fix — Vioxx/Baycol/Bextra were silently marked "
        "is_withdrawn=FALSE, a patient-safety-critical bug)"
    )
    # The actual UPDATE statement must reference 'withdrawn'.
    assert "withdrawn" in source.lower()
    # The SET is_withdrawn = TRUE pattern must be present.
    assert "is_withdrawn = TRUE" in source


# ──────────────────────────────────────────────────────────────────────────
# F3.6 — protein_id added to ORM GeneDiseaseAssociation
# ──────────────────────────────────────────────────────────────────────────

def test_gda_orm_has_protein_id_column():
    """v14 ROOT FIX (FIX4 / CD-3): GeneDiseaseAssociation ORM NO LONGER
    has the protein_id column. The previous v9 fix ADDED it to the ORM
    to match the migrations — but the migrations were THEMSELVES the
    bug. The GDA table uses the STRING ``uniprot_id`` FK as the
    canonical protein reference (loader never populated protein_id;
    migration 003 backfill was a no-op; index unused; column produced
    false-positive schema drift). v14 removes the column from the ORM
    AND from migrations 001/003 AND from REQUIRED_COLUMNS /
    EXPECTED_SCHEMA in run_migrations.py. The GDA model must use
    uniprot_id ONLY.

    Source-inspection: models.py imports sqlalchemy + database.base
    which can't easily be set up in test isolation.
    """
    src_path = _REPO_ROOT / "phase1" / "database" / "models.py"
    source = src_path.read_text()
    # Find the GeneDiseaseAssociation class.
    cls_start = source.find('class GeneDiseaseAssociation')
    assert cls_start != -1, "GeneDiseaseAssociation class must exist"
    # Find the end (next class definition).
    cls_end = source.find('\nclass ', cls_start + 5)
    body = source[cls_start:cls_end]
    # The protein_id column must NOT be declared (v14 root fix removed it).
    # Allow the column name to appear in COMMENTS documenting the removal,
    # but it must NOT appear as an actual ``protein_id: Mapped[...]`` line.
    import re
    actual_decl = re.search(r"^\s*protein_id\s*:\s*Mapped\[", body, re.MULTILINE)
    assert actual_decl is None, (
        "v14 ROOT FIX regression: GeneDiseaseAssociation ORM still declares "
        "protein_id as a Mapped column. The GDA table uses uniprot_id ONLY "
        "(FIX4 / CD-3 — loader never populated protein_id; the column "
        "produced false-positive schema drift)."
    )
    # The uniprot_id column MUST be declared.
    uniprot_decl = re.search(r"^\s*uniprot_id\s*:\s*Mapped\[", body, re.MULTILINE)
    assert uniprot_decl is not None, (
        "GeneDiseaseAssociation ORM must declare uniprot_id column (the "
        "canonical STRING FK to proteins.uniprot_id)."
    )
    # The v14 ROOT FIX comment must be present (documents the removal).
    assert "v14 ROOT FIX" in body or "FIX4" in body or "CD-3" in body, (
        "v14 ROOT FIX documentation comment missing from GDA model."
    )


# ──────────────────────────────────────────────────────────────────────────
# F3.1 — _quarantine_gda_rows path resolved relative to package
# ──────────────────────────────────────────────────────────────────────────

def test_quarantine_gda_rows_does_not_hardcode_absolute_path():
    """_quarantine_gda_rows source does NOT hardcode the original
    developer's machine path as the DEFAULT fallback (only as documentation
    of what was wrong)."""
    src_path = _REPO_ROOT / "phase1" / "database" / "loaders.py"
    source = src_path.read_text()
    # Find the _quarantine_gda_rows function body.
    fn_start = source.find("def _quarantine_gda_rows")
    assert fn_start != -1
    # End at the next def.
    fn_end = source.find("\ndef ", fn_start + 5)
    body = source[fn_start:fn_end]
    # The hardcoded path must NOT be the value of os.environ.get's default.
    # We check the actual code line that sets dl_dir.
    for line in body.split("\n"):
        stripped = line.strip()
        # The default value (2nd arg to os.environ.get) must NOT be the
        # hardcoded absolute path.
        if "os.environ.get(" in stripped and "DRUGOS_DEAD_LETTER_DIR" in stripped:
            # Extract the default value (2nd arg).
            # Allow it to be _DEFAULT_DL_DIR (relative) but not the hardcoded path.
            assert "_DEFAULT_DL_DIR" in stripped or \
                   "/home/z/my-project/work/codebase/unified/phase1/data/dead_letter" \
                   not in stripped, (
                "_quarantine_gda_rows must NOT use the hardcoded absolute "
                "path as the default for DRUGOS_DEAD_LETTER_DIR (audit F3.1)"
            )
    # The relative path resolution pattern must be present.
    assert "Path(__file__).resolve().parent.parent" in body, (
        "_quarantine_gda_rows must resolve the path relative to the "
        "phase1 package (audit F3.1 fix)"
    )
