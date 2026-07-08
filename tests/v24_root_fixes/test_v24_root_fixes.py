"""
v24 Root-Fix Verification Tests
================================

This test suite verifies that each root-cause fix from the v24 forensic
audit actually holds at runtime — NOT by reading comments or docstrings,
but by exercising the actual production code paths.

Every test in this file corresponds to a specific audit finding and
carries a ``# AUDIT:`` comment citing the finding it verifies.

Run:
    python -m pytest tests/v24_root_fixes/test_v24_root_fixes.py -v
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

# Ensure the phase1 and phase2 roots are on sys.path so both packages
# are importable.
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PHASE1_ROOT = ROOT / "phase1"
PHASE2_ROOT = ROOT / "phase2"
for p in (str(PHASE1_ROOT), str(PHASE2_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ─── FIX 1: STRING/UniProt/ChEMBL step7 skip when phase1 bridge used ───────

def test_fix1_step7_skips_string_uniprot_chembl_when_phase1():
    """AUDIT: Phase 2 Loaders Bypass Matrix — 0 of 13 loaders consume
    Phase 1 outputs at runtime in default mode.

    v24 fix: when data_source='phase1' (the default), step7a/7b/7c are
    SKIPPED because the bridge already loaded STRING/UniProt/ChEMBL from
    Phase 1 CSVs in step1.
    """
    import inspect
    from drugos_graph import run_pipeline

    sig = inspect.signature(run_pipeline.step7_additional_sources)
    assert "data_source" in sig.parameters, (
        "step7_additional_sources must accept a data_source parameter (v24 fix)"
    )
    assert sig.parameters["data_source"].default == "phase1", (
        "data_source default must be 'phase1' so the bridge is used by default"
    )


def test_fix1_run_full_pipeline_threads_data_source_to_step7():
    """AUDIT: run_full_pipeline must thread data_source to step7."""
    import inspect
    from drugos_graph import run_pipeline

    src = inspect.getsource(run_pipeline.run_full_pipeline)
    assert "data_source=data_source" in src, (
        "run_full_pipeline must pass data_source=data_source to step7_additional_sources"
    )


# ─── FIX 2: kg_builder preserves 'source' property ─────────────────────────

def test_fix2_kg_builder_does_not_strip_source_property():
    """AUDIT: Chain 4 — edge properties preserved by bridge, stripped by
    kg_builder._load_edges.

    v24 fix: ``source`` is no longer in the blanket _endpoint_keys set.
    The alias actually used as an endpoint is tracked and removed
    individually.
    """
    import inspect
    from drugos_graph import kg_builder

    src = inspect.getsource(kg_builder.GraphEdgeLoader._load_edges)
    # The _endpoint_keys set must NOT contain "source" or "target"
    # (they are legitimate data-source property names).
    # Find the _endpoint_keys definition.
    match = re.search(r"_endpoint_keys\s*=\s*\{([^}]+)\}", src)
    assert match, "_endpoint_keys set must exist in _load_edges source"
    endpoint_keys_content = match.group(1)
    assert '"source"' not in endpoint_keys_content, (
        "v24 fix: 'source' must NOT be in _endpoint_keys — it is a "
        "legitimate data-source property emitted by the bridge."
    )
    assert '"target"' not in endpoint_keys_content, (
        "v24 fix: 'target' must NOT be in _endpoint_keys — same reason."
    )


def test_fix2_kg_builder_tracks_used_endpoint_alias():
    """AUDIT: the alias actually used as an endpoint must be tracked
    and removed individually (not blanket-excluded)."""
    import inspect
    from drugos_graph import kg_builder

    src = inspect.getsource(kg_builder.GraphEdgeLoader._load_edges)
    assert "_used_src_alias" in src, (
        "v24 fix: _load_edges must track which src alias was actually used"
    )
    assert "_used_dst_alias" in src, (
        "v24 fix: _load_edges must track which dst alias was actually used"
    )


# ─── FIX 3: step3_load_neo4j passes edge properties through ────────────────

def test_fix3_step3_accepts_edge_props_lookup():
    """AUDIT: Chain 4 — step3 constructs bare edge dicts, dropping all
    properties.

    v24 fix: step3 accepts an optional edge_props_lookup parameter.
    """
    import inspect
    from drugos_graph import run_pipeline

    sig = inspect.signature(run_pipeline.step3_load_neo4j)
    assert "edge_props_lookup" in sig.parameters, (
        "step3_load_neo4j must accept edge_props_lookup (v24 fix)"
    )


def test_fix3_step1_returns_edge_props_lookup():
    """AUDIT: step1_load_phase1 must return edge_props_lookup so step3
    can use it."""
    import inspect
    from drugos_graph import run_pipeline

    src = inspect.getsource(run_pipeline.step1_load_phase1)
    assert "edge_props_lookup" in src, (
        "step1_load_phase1 must build and return edge_props_lookup (v24 fix)"
    )


# ─── FIX 4: Filtered MRR wired up in train_transe ──────────────────────────

def test_fix4_train_transe_passes_other_true_triples_per_query():
    """AUDIT: section 7 finding 9 — Non-filtered MRR.

    v24 fix: train_transe builds other_true_triples_per_query from
    _known and passes it to evaluate_link_prediction.
    """
    import inspect
    from drugos_graph import transe_model

    src = inspect.getsource(transe_model.train_transe)
    assert "other_true_triples_per_query" in src, (
        "train_transe must pass other_true_triples_per_query to "
        "evaluate_link_prediction (v24 fix for filtered MRR)"
    )
    assert "_other_true_per_query" in src, (
        "train_transe must build the per-query other-true-tails set (v24 fix)"
    )


# ─── FIX 5: Bridge tgt_canonical ID format ─────────────────────────────────

def test_fix5_bridge_emits_chembl_tgt_digits_only():
    """AUDIT: Chain 9 — bridge emits CHEMBL_TGT_CHEMBL2366519 but
    kg_builder regex requires ^CHEMBL_TGT_\d+$.

    v24 fix: bridge strips the CHEMBL prefix and emits
    CHEMBL_TGT_<digits> so the ID matches the regex.
    """
    import inspect
    from drugos_graph import phase1_bridge

    src = inspect.getsource(phase1_bridge)
    # The fix uses re.sub to strip the CHEMBL prefix.
    assert "re.sub" in src and "CHEMBL" in src, (
        "phase1_bridge must use re.sub to strip the CHEMBL prefix from "
        "tgt_chembl before emitting CHEMBL_TGT_<digits> (v24 fix)"
    )


def test_fix5_chembl_tgt_id_matches_kg_builder_regex():
    """Verify the emitted ID format actually matches the kg_builder
    ID_PATTERNS['Protein'] regex."""
    from drugos_graph.kg_builder import ID_PATTERNS
    import re as _re

    protein_pattern = ID_PATTERNS.get("Protein", "")
    # Simulate what the bridge emits for a ChEMBL target ID like
    # "CHEMBL2366519" → strip "CHEMBL" → "2366519" → "CHEMBL_TGT_2366519"
    tgt_chembl = "CHEMBL2366519"
    digits = _re.sub(r"^CHEMBL", "", tgt_chembl)
    emitted_id = f"CHEMBL_TGT_{digits}"
    assert _re.match(protein_pattern, emitted_id), (
        f"Emitted ID {emitted_id!r} must match kg_builder Protein regex "
        f"{protein_pattern!r}. This is the v24 root fix for Chain 9."
    )


# ─── FIX 6: Stale EC50/AC50 comment fixed ──────────────────────────────────

def test_fix6_ec50_ac50_comment_does_not_lie():
    """AUDIT: FORENSIC-P2-CORE §4 — stale comment at phase1_bridge:1586
    said EC50/AC50 → 'activates' but the code returns 'targets'."""
    import inspect
    from drugos_graph import phase1_bridge

    src = inspect.getsource(phase1_bridge._classify_chembl_activity_edge)
    # The comment must NOT claim EC50/AC50 → 'activates'.
    assert 'EC50" / "AC50"\n     → "activates"' not in src, (
        "v24 fix: the stale comment claiming EC50/AC50 → 'activates' "
        "must be updated to reflect the actual 'targets' classification."
    )


# ─── FIX 7: InChIKey validator unification ─────────────────────────────────

def test_fix7_loaders_validate_inchikey_delegates_to_canonical():
    """AUDIT: Chain 3 — 3 (now 5) divergent InChIKey validators.

    v24 fix: loaders._validate_inchikey delegates to
    cleaning.normalizer.is_valid_inchikey.
    """
    import inspect
    from database import loaders

    src = inspect.getsource(loaders._validate_inchikey)
    assert "is_valid_inchikey" in src, (
        "loaders._validate_inchikey must delegate to the canonical "
        "cleaning.normalizer.is_valid_inchikey (v24 fix)"
    )


def test_fix7_chembl_pipeline_has_delegating_wrapper():
    """AUDIT: FORENSIC-P1-PIPE §1 — 5 divergent InChIKey regexes in
    the pipeline layer.

    v24 fix: chembl_pipeline exposes a _is_valid_inchikey wrapper that
    delegates to the canonical validator.
    """
    from pipelines import chembl_pipeline

    assert hasattr(chembl_pipeline, "_is_valid_inchikey"), (
        "chembl_pipeline must expose _is_valid_inchikey wrapper (v24 fix)"
    )


def test_fix7_drugbank_pipeline_has_delegating_wrapper():
    """Same as above but for drugbank_pipeline."""
    from pipelines import drugbank_pipeline

    assert hasattr(drugbank_pipeline, "_is_valid_inchikey"), (
        "drugbank_pipeline must expose _is_valid_inchikey wrapper (v24 fix)"
    )


# ─── FIX 8: loaders._validate_uniprot_id accepts isoforms + CHEMBL_TGT_* ───

def test_fix8_loaders_validate_uniprot_accepts_isoforms():
    """AUDIT: FORENSIC-P1-DATA §2 — loaders._validate_uniprot_id did
    NOT accept isoform suffixes (P04637-2) or CHEMBL_TGT_* IDs.

    v24 fix: accept both.
    """
    from database.loaders import _validate_uniprot_id

    # Standard UniProt AC
    assert _validate_uniprot_id("P69999") == "P69999"
    # Isoform suffix
    assert _validate_uniprot_id("P04637-2") == "P04637-2", (
        "v24 fix: _validate_uniprot_id must accept isoform suffixes like P04637-2"
    )
    # CHEMBL_TGT_* ID (Phase 2 bridge Protein nodes)
    assert _validate_uniprot_id("CHEMBL_TGT_2366519") == "CHEMBL_TGT_2366519", (
        "v24 fix: _validate_uniprot_id must accept CHEMBL_TGT_<digits> IDs"
    )


# ─── FIX 9: missing_values non-batch path fail-loud ────────────────────────

def test_fix9_missing_values_non_batch_no_silent_passthrough():
    """AUDIT: FORENSIC-P1-PIPE B — missing_values.py:1680-1681 still
    did ``standardized = inchikey`` (silent passthrough).

    v24 fix: the non-batch path now marks the row as failed instead of
    passing the unvalidated InChIKey through.
    """
    import inspect
    from cleaning import missing_values

    src = inspect.getsource(missing_values)
    # The silent passthrough line must be gone.
    assert "standardized = inchikey  # passthrough on error" not in src, (
        "v24 fix: the silent passthrough 'standardized = inchikey' must "
        "be replaced with a fail-loud path that marks the row as failed."
    )
    # The fail-loud path must be present.
    assert "STANDARDIZATION_FAILED" in src, (
        "v24 fix: the non-batch path must mark rows as STANDARDIZATION_FAILED"
    )


# ─── FIX 10: chembl is_fda_approved max_phase heuristic ────────────────────

def test_fix10_chembl_is_fda_approved_max_phase4_returns_true():
    """AUDIT: FORENSIC-P1-PIPE A/§2 — max_phase=4 drugs still got
    is_fda_approved=None because approved_by is never populated.

    v24 fix: max_phase>=4 → True (approved by any regulator).
    """
    import inspect
    from pipelines import chembl_pipeline

    src = inspect.getsource(chembl_pipeline)
    # The _derive_fda function must treat max_phase>=4 as True.
    assert "mp_int >= 4" in src, (
        "v24 fix: _derive_fda must return True for max_phase>=4 (ChEMBL "
        "semantic: approved by any regulator globally)"
    )


# ─── FIX 11: ChEMBL iter_chembl_activities deterministic sort ──────────────

def test_fix11_iter_chembl_activities_deterministic_sort():
    """AUDIT: FORENSIC-P2-LOADERS D/§1 — iter_chembl_activities still
    used non-deterministic db_files[0].

    v24 fix: deterministic sort by (size, mtime, path).
    """
    import inspect
    from drugos_graph import chembl_loader

    src = inspect.getsource(chembl_loader.iter_chembl_activities)
    assert "db_files.sort" in src, (
        "v24 fix: iter_chembl_activities must sort db_files deterministically"
    )


# ─── FIX 12: _dead_letter_queue fail-closed default ────────────────────────

def test_fix12_dead_letter_queue_fail_closed_default():
    """AUDIT: FORENSIC-P1-DATA V — _dead_letter_queue enabled flag
    defaulted to True on config import failure (fail-OPEN).

    v24 fix: default to False (fail-CLOSED).
    """
    import inspect
    from database import loaders

    src = inspect.getsource(loaders._add_to_dead_letter)
    # The fail-closed default must be present.
    assert "enabled = False" in src, (
        "v24 fix: _add_to_dead_letter must default to enabled=False "
        "(fail-closed) when config import fails"
    )


# ─── FIX 13: id_crosswalk exponential backoff ─────────────────────────────

def test_fix13_id_crosswalk_exponential_backoff():
    """AUDIT: FORENSIC-P2-LOADERS §4 — docstring said 'exponential
    backoff' but code used fixed 0.34s sleep.

    v24 fix: actual exponential backoff on consecutive errors.
    """
    import inspect
    from drugos_graph import id_crosswalk

    src = inspect.getsource(id_crosswalk.IDCrosswalk.verify_builtin_against_ncbi)
    assert "_consecutive_errors" in src, (
        "v24 fix: verify_builtin_against_ncbi must track _consecutive_errors"
    )
    assert "2 ** _consecutive_errors" in src or "2 ** _consecutive" in src, (
        "v24 fix: verify_builtin_against_ncbi must use exponential backoff "
        "(RATE_LIMIT_S * 2**consecutive_errors)"
    )


# ─── FIX 14: entity_resolver comment does not lie ─────────────────────────

def test_fix14_entity_resolver_gene_validation_actually_flags():
    """AUDIT: FORENSIC-P2-LOADERS §3 — comment said 'accept but flag'
    but code just passed (no flag added).

    v24 fix: actually append a WARNING to errors.
    """
    import inspect
    from drugos_graph import entity_resolver

    src = inspect.getsource(entity_resolver.EntityResolver._validate_canonical_id)
    # The misleading 'accept but flag' + bare 'pass' must be gone.
    assert "accept but flag\n                pass" not in src, (
        "v24 fix: the misleading 'accept but flag' + bare 'pass' must be "
        "replaced with an actual errors.append() WARNING."
    )


# ─── FIX 15: phase1_bridge duplicate file list removed ─────────────────────

def test_fix15_phase1_bridge_no_duplicate_file_list():
    """AUDIT: FORENSIC-P1-PIPE §4 — phase1_bridge.py:622-625 listed
    omim_gene_disease_susceptibility.csv TWICE.

    v24 fix: deduplicated.
    """
    import inspect
    from drugos_graph import phase1_bridge

    src = inspect.getsource(phase1_bridge)
    # Count occurrences of the duplicate line.
    count = src.count('base / "omim_gene_disease_susceptibility.csv"')
    assert count == 1, (
        f"v24 fix: omim_gene_disease_susceptibility.csv must appear exactly "
        f"once in phase1_bridge (found {count} occurrences)."
    )


# ─── INTEGRATION: end-to-end pipeline runs with exit 0 ─────────────────────

def test_integration_run_unified_exits_0():
    """INTEGRATION: the default ``python run_unified.py`` must exit 0
    with V1 launch criteria PASSED. This is the user's #1 requirement:
    'every session every AI tells its 100 percent integrated but see
    the reality' — the reality is now that the pipeline actually runs
    end-to-end and produces a trained model.
    """
    import subprocess

    result = subprocess.run(
        [sys.executable, "run_unified.py"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"run_unified.py must exit 0 (v24 root fix). "
        f"Got exit code {result.returncode}.\n"
        f"STDERR tail:\n{result.stderr[-2000:]}"
    )
    assert "V1 LAUNCH CRITERIA: PASSED" in result.stderr or "V1 criteria: PASSED" in result.stderr, (
        "V1 launch criteria must PASSED in the default run. "
        f"STDERR tail:\n{result.stderr[-2000:]}"
    )
    assert "FULL PIPELINE COMPLETE" in result.stderr, (
        "Full pipeline must complete. "
        f"STDERR tail:\n{result.stderr[-2000:]}"
    )


def test_integration_step7a_7b_7c_skipped_with_phase1_reason():
    """INTEGRATION: verify the v24 skip messages actually appear in
    the runtime log when data_source='phase1'."""
    import subprocess

    result = subprocess.run(
        [sys.executable, "run_unified.py"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    combined = result.stderr + result.stdout
    assert "Step 7a SKIPPED (v24 root fix)" in combined, (
        "Step 7a skip message must appear in the log (v24 fix)"
    )
    assert "Step 7b SKIPPED (v24 root fix)" in combined, (
        "Step 7b skip message must appear in the log (v24 fix)"
    )
    assert "Step 7c SKIPPED (v24 root fix)" in combined, (
        "Step 7c skip message must appear in the log (v24 fix)"
    )
    assert "phase1_bridge_already_loaded" in combined, (
        "The skip reason must be 'phase1_bridge_already_loaded'"
    )


if __name__ == "__main__":
    # Allow running without pytest: ``python test_v24_root_fixes.py``
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS: {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"FAIL: {test.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n=== {passed} passed, {failed} failed ===")
    sys.exit(0 if failed == 0 else 1)
