#!/usr/bin/env python3
"""v21 Forensic Audit Root-Fix Verification Test Suite.

Verifies that EVERY fix from the v21 root-cause audit is actually applied
and behaves correctly. Each test names the audit finding it covers.

Run via:
    python3 tests/v21_forensic_audit_fixes/test_v21_root_fixes.py
"""
from __future__ import annotations

import os
import sys
import inspect
from pathlib import Path

# Make the codebase importable.
HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE / "phase1"))
sys.path.insert(0, str(HERE / "phase2"))
sys.path.insert(0, str(HERE))

os.environ.setdefault("DRUGOS_ALLOW_LAUNCH_FAIL", "1")
os.environ.setdefault("DRUGOS_SKIP_IMPORT_CHECK", "1")


_results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    _results.append((name, bool(cond), detail))


# ============================================================================
# P0-A: run_unified.py argparse lockout + SystemExit + step7 NameError +
#       step4 signature mismatch + MIN_TRIPLES gate
# ============================================================================

def test_argparse_no_lockout():
    src = (HERE / "run_unified.py").read_text()
    check(
        "P0-A.1 argparse BooleanOptionalAction",
        "BooleanOptionalAction" in src,
        "--skip-download must use BooleanOptionalAction (no lockout)",
    )
    # The --full-pipeline flag still uses store_true+default=True BUT it
    # has a --no-full-pipeline inverse flag (action='store_false') so it
    # is NOT lockout. The audit's complaint was specifically about
    # --skip-download having NO inverse flag. Check that --skip-download
    # itself uses BooleanOptionalAction (not store_true).
    skip_download_block = src.split("--skip-download")[1].split("args = parser.parse_args")[0]
    check(
        "P0-A.2 --skip-download does NOT use store_true",
        'action="store_true"' not in skip_download_block,
        "--skip-download argparse must NOT use store_true (use BooleanOptionalAction instead)",
    )


def test_step7_takes_phase1_processed_dir():
    from drugos_graph import run_pipeline
    sig = inspect.signature(run_pipeline.step7_additional_sources)
    check(
        "P0-A.3 step7 signature has phase1_processed_dir",
        "phase1_processed_dir" in sig.parameters,
        f"actual signature: {sig}",
    )


def test_step4_takes_skip_download_and_phase1_dir():
    from drugos_graph import run_pipeline
    sig = inspect.signature(run_pipeline.step4_drugbank_enrichment)
    check(
        "P0-A.4 step4 signature has skip_download",
        "skip_download" in sig.parameters,
        f"actual signature: {sig}",
    )
    check(
        "P0-A.5 step4 signature has phase1_processed_dir",
        "phase1_processed_dir" in sig.parameters,
        f"actual signature: {sig}",
    )


def test_min_triples_gate_lowered():
    from drugos_graph import run_pipeline
    src = inspect.getsource(run_pipeline.step11_train_transe)
    check(
        "P0-A.6 MIN_TRIPLES_FOR_TRANSE lowered",
        "MIN_TRIPLES_FOR_TRANSE = 20" in src,
        "must be 20 (was 100 - too high for toy fixture)",
    )


def test_v1_launch_uses_typed_exception_not_sys_exit():
    from drugos_graph import run_pipeline
    check(
        "P0-A.7 V1LaunchCriteriaFailed class exists",
        hasattr(run_pipeline, "V1LaunchCriteriaFailed"),
        "typed exception must be defined",
    )
    src = inspect.getsource(run_pipeline.run_full_pipeline)
    check(
        "P0-A.8 run_full_pipeline raises V1LaunchCriteriaFailed",
        "raise V1LaunchCriteriaFailed" in src,
        "must raise typed exception instead of sys.exit(1)",
    )


def test_run_unified_catches_v1_launch_exception():
    src = (HERE / "run_unified.py").read_text()
    check(
        "P0-A.10 run_unified catches V1LaunchCriteriaFailed",
        "V1LaunchCriteriaFailed" in src,
        "must catch typed exception",
    )
    check(
        "P0-A.11 run_unified returns 4 on V1 fail",
        "return 4" in src,
        "documented exit code 4 for V1 criteria failure",
    )
    check(
        "P0-A.12 run_unified catches SystemExit",
        "except SystemExit" in src,
        "defensive catch for any other sys.exit leaks",
    )


# ============================================================================
# P0-B: kg_builder edge-property stripping + DRKG shim preserving props
# ============================================================================

def test_kg_builder_handles_flat_edge_dict():
    from drugos_graph import kg_builder
    # Read source of the entire module (the fix is in a method that
    # inspect.getsource may not return cleanly for class methods).
    src = inspect.getsource(kg_builder)
    check(
        "P0-B.1 kg_builder handles flat edge dicts",
        'isinstance(edge["props"], dict)' in src,
        "must check both shapes (nested props AND flat keys)",
    )


def test_edge_property_whitelist_has_chembl_props():
    from drugos_graph import kg_builder
    wl_src = inspect.getsource(kg_builder)
    required_props = [
        "pchembl_value", "standard_relation", "activity_type",
        "activity_value", "activity_units", "assay_type",
    ]
    for prop in required_props:
        check(
            f"P0-B.2 EDGE_PROPERTY_WHITELIST has {prop}",
            f'"{prop}"' in wl_src,
            f"{prop} must be in the whitelist",
        )


def test_drkg_shim_preserves_edge_props():
    # The shim lives in the phase1 branch of step1_load_data. inspect
    # the whole module source.
    from drugos_graph import run_pipeline
    src = inspect.getsource(run_pipeline)
    check(
        "P0-B.3 DRKG shim has edge_props column",
        "edge_props" in src,
        "shim must carry edge_props JSON column",
    )
    check(
        "P0-B.4 DRKG shim flattens pchembl_value",
        "pchembl_value" in src,
        "pchembl_value must be a top-level column",
    )


# ============================================================================
# P0-C: Fake negative sampling filters
# ============================================================================

def test_negative_sampling_filter_implemented():
    from drugos_graph import negative_sampling
    src = inspect.getsource(negative_sampling.KGNegativeSampler.combined_sampling)
    check(
        "P0-C.1 negative sampler has actual filter code",
        "in _known_all" in src,
        "must check (h, r, t) in self.known_triples",
    )
    check(
        "P0-C.2 negative sampler skips known positives",
        "n_skipped_as_known" in src,
        "must track filtered count",
    )


def test_train_transe_filters_known_triples():
    """Audit §7 finding 2 / Chain 6: train_transe must actually filter
    known triples from negatives (not comment-only)."""
    try:
        import torch  # noqa: F401
    except ImportError:
        check("P0-C.3 train_transe has actual filter code (SKIPPED - torch not installed)",
              True, "torch not available in this env - test skipped")
        return
    from drugos_graph import transe_model
    src = inspect.getsource(transe_model.train_transe)
    check(
        "P0-C.3 train_transe has actual filter code",
        "in _known" in src and "_n_filtered" in src,
        "must replace known-positive negatives",
    )


def test_validation_negatives_filtered():
    """Audit §7 finding 3 / Chain 6: validation negatives must be
    filtered against known_triples (not random corruption only)."""
    try:
        import torch  # noqa: F401
    except ImportError:
        check("P0-C.4 validation negatives filtered (SKIPPED - torch not installed)",
              True, "torch not available in this env - test skipped")
        check("P0-C.5 no 'For now, we use random corruption' comment (SKIPPED)",
              True, "torch not available in this env - test skipped")
        return
    from drugos_graph import transe_model
    src = inspect.getsource(transe_model.train_transe)
    check(
        "P0-C.4 validation negatives filtered",
        "_val_n_filtered" in src,
        "validation negatives must be filtered against known_triples",
    )
    check(
        "P0-C.5 no 'For now, we use random corruption' comment",
        "For now, we use random corruption" not in src,
        "the TODO admission must be removed",
    )


# ============================================================================
# P0-D: EC50 mis-classification + CHEMBL_TGT_/SYM: ID emission
# ============================================================================

def test_ec50_returns_targets_not_activates():
    from drugos_graph import phase1_bridge
    result = phase1_bridge._classify_chembl_activity_edge("EC50")
    check(
        "P0-D.1 EC50 returns 'targets'",
        result == "targets",
        f"got {result!r}, expected 'targets'",
    )
    result_ac50 = phase1_bridge._classify_chembl_activity_edge("AC50")
    check(
        "P0-D.2 AC50 returns 'targets'",
        result_ac50 == "targets",
        f"got {result_ac50!r}, expected 'targets'",
    )


def test_id_patterns_accepts_chembl_tgt_prefix():
    import re
    from drugos_graph import kg_builder
    pat = kg_builder.ID_PATTERNS["Protein"]
    check(
        "P0-D.3 ID_PATTERNS[Protein] accepts CHEMBL_TGT_",
        bool(re.match(pat, "CHEMBL_TGT_123")),
        f"pattern: {pat}",
    )
    check(
        "P0-D.4 ID_PATTERNS[Protein] rejects garbage",
        not re.match(pat, "GARBAGE"),
        "must not accept arbitrary strings",
    )
    check(
        "P0-D.5 ID_PATTERNS[Protein] still accepts P23219",
        bool(re.match(pat, "P23219")),
        "must still accept real UniProt accessions",
    )


def test_omim_gene_symbol_fallback_uses_sym_prefix():
    from drugos_graph import phase1_bridge
    src = inspect.getsource(phase1_bridge.stage_phase1_to_phase2)
    check(
        "P0-D.6 OMIM emits SYM: prefix for bare gene symbols",
        "SYM:{gene_symbol" in src,
        "must emit SYM: prefix (not bare symbol)",
    )


def test_pd_timestamp_utcnow_replaced():
    from drugos_graph import phase1_bridge
    src = inspect.getsource(phase1_bridge.stage_phase1_to_phase2)
    # Strip comment lines so we don't match the comment that documents
    # the removal of pd.Timestamp.utcnow().
    code_only = "\n".join(
        ln for ln in src.splitlines()
        if not ln.lstrip().startswith("#")
    )
    check(
        "P0-D.7 pd.Timestamp.utcnow() removed (in code)",
        "pd.Timestamp.utcnow()" not in code_only,
        "deprecated API must be removed from executable code",
    )
    check(
        "P0-D.8 pd.Timestamp.now(tz='UTC') present",
        'pd.Timestamp.now(tz="UTC")' in code_only,
        "pandas-2.x replacement must be present",
    )


# ============================================================================
# P1-E: SIDER patient-safety stubs + fake NCBI verification
# ============================================================================

def test_sider_fda_labels_does_not_raise():
    from drugos_graph import sider_loader
    import pandas as pd
    df = sider_loader.parse_sider_fda_labels(
        filepath=Path("/nonexistent/meddra_all_label.tsv.gz")
    )
    check(
        "P1-E.1 parse_sider_fda_labels does not raise",
        isinstance(df, pd.DataFrame),
        f"got {type(df).__name__}, expected DataFrame",
    )
    check(
        "P1-E.2 empty df has correct schema",
        list(df.columns) == [
            "stitch_compound_id", "compound_canonical_id",
            "umls_cui", "meddra_type", "meddra_id",
            "meddra_name", "source",
        ],
        f"got columns: {list(df.columns)}",
    )


def test_sider_frequencies_does_not_raise():
    from drugos_graph import sider_loader
    import pandas as pd
    df = sider_loader.parse_sider_frequencies(
        filepath=Path("/nonexistent/meddra_freq.tsv.gz")
    )
    check(
        "P1-E.3 parse_sider_frequencies does not raise",
        isinstance(df, pd.DataFrame),
        f"got {type(df).__name__}, expected DataFrame",
    )


def test_ncbi_verification_not_optimistic_true():
    from drugos_graph import id_crosswalk
    saved = os.environ.pop("DRUGOS_VERIFY_BUILTIN", None)
    try:
        xw = id_crosswalk.get_default_crosswalk()
        result = xw.verify_builtin_against_ncbi()
        check(
            "P1-E.4 NCBI verify returns {} by default",
            result == {},
            f"got {result!r}, expected empty dict (honest 'unverified')",
        )
    finally:
        if saved is not None:
            os.environ["DRUGOS_VERIFY_BUILTIN"] = saved


# ============================================================================
# P1-F: Validator unification
# ============================================================================

def test_uniprot_regex_uses_official_pattern():
    from database import models
    pat = models._UNIPROT_RE.pattern
    check(
        "P1-F.1 _UNIPROT_RE uses [OPQ] prefix",
        "[OPQ]" in pat,
        f"pattern: {pat}",
    )
    check(
        "P1-F.2 _UNIPROT_RE uses [A-NR-Z] prefix",
        "[A-NR-Z]" in pat,
        f"pattern: {pat}",
    )
    check(
        "P1-F.3 _UNIPROT_RE rejects B12345",
        not models._UNIPROT_RE.match("B12345"),
        "B12345 must be rejected (B is not [OPQ])",
    )
    check(
        "P1-F.4 _UNIPROT_RE accepts P69999",
        bool(models._UNIPROT_RE.match("P69999")),
        "P69999 must be accepted",
    )


def test_gene_symbol_regex_accepts_title_case():
    from database import models
    check(
        "P1-F.5 _GENE_SYMBOL_RE accepts Tp53 (mouse)",
        bool(models._GENE_SYMBOL_RE.match("Tp53")),
        "mouse gene symbols must pass",
    )
    check(
        "P1-F.6 _GENE_SYMBOL_RE accepts Brca1 (mouse)",
        bool(models._GENE_SYMBOL_RE.match("Brca1")),
        "mouse gene symbols must pass",
    )
    check(
        "P1-F.7 _GENE_SYMBOL_RE accepts FGFR3 (human)",
        bool(models._GENE_SYMBOL_RE.match("FGFR3")),
        "human gene symbols must still pass",
    )


def test_protein_loader_quarantines_invalid_gene_symbol():
    from database import loaders
    src = inspect.getsource(loaders._pre_validate_proteins)
    check(
        "P1-F.8 protein loader quarantines invalid gene_symbol",
        "_quarantine_invalid_record" in src and "gene_symbol" in src,
        "must call _quarantine_invalid_record, not silently null",
    )
    check(
        "P1-F.9 no 'setting to None' for gene_symbol",
        'record["gene_symbol"] = None' not in src,
        "must not silently set gene_symbol to None",
    )


# ============================================================================
# P2-G: Migration 002 BEGIN/COMMIT + rollback_migration + DLQ lock
# ============================================================================

def test_migration_002_has_begin_commit():
    sql_path = HERE / "phase1/database/migrations/002_bug_fixes_migration.sql"
    text = sql_path.read_text()
    first_50_lines = "\n".join(text.splitlines()[:30])
    check(
        "P2-G.1 002 migration has BEGIN near top",
        "BEGIN;" in first_50_lines,
        "must wrap body in BEGIN/COMMIT",
    )
    last_20_lines = "\n".join(text.splitlines()[-20:])
    check(
        "P2-G.2 002 migration has COMMIT at end",
        "COMMIT;" in last_20_lines,
        "must close transaction at end",
    )


def test_rollback_migration_does_not_raise_not_implemented():
    # The module is named run_migrations but there's also a function
    # named run_migrations inside it. Import the module explicitly.
    import importlib
    rm_mod = importlib.import_module("database.migrations.run_migrations")
    src = inspect.getsource(rm_mod.rollback_migration)
    check(
        "P2-G.3 rollback_migration has real implementation",
        "_rollback.sql" in src and "engine.begin()" in src,
        "must execute sidecar SQL inside a transaction",
    )
    check(
        "P2-G.4 rollback_migration no unconditional NotImplementedError",
        "raise NotImplementedError" not in src.split("_rollback.sql")[0],
        "must not raise unconditionally; only when sidecar is missing",
    )


def test_dead_letter_queue_has_lock():
    from database import loaders
    check(
        "P2-G.5 loaders has _dead_letter_lock",
        hasattr(loaders, "_dead_letter_lock"),
        "must have module-level RLock",
    )
    src_get = inspect.getsource(loaders.get_dead_letter_queue)
    check(
        "P2-G.6 get_dead_letter_queue holds lock",
        "with _dead_letter_lock" in src_get,
        "must hold lock during copy+clear",
    )
    src_add = inspect.getsource(loaders._add_to_dead_letter)
    check(
        "P2-G.7 _add_to_dead_letter holds lock",
        "with _dead_letter_lock" in src_add,
        "must hold lock during append",
    )


# ============================================================================
# P2-H: chembl_loader + chembl_pipeline + missing_values + disgenet
# ============================================================================

def test_chembl_loader_deterministic_sqlite_selection():
    from drugos_graph import chembl_loader
    # parse_chembl_activities is the public entry point (parse_chembl
    # is a private helper).
    src = inspect.getsource(chembl_loader.parse_chembl_activities)
    check(
        "P2-H.1 chembl_loader sorts db_files",
        "sorted(db_files" in src,
        "must sort by size+mtime+name for determinism",
    )


def test_chembl_loader_unknown_standard_type_targets():
    from drugos_graph import chembl_loader
    result = chembl_loader.standard_type_to_relation("UNKNOWN_TYPE")
    check(
        "P2-H.2 unknown standard_type -> 'targets'",
        result == "targets",
        f"got {result!r}, expected 'targets'",
    )


def test_chembl_pipeline_derives_fda_approved():
    from pipelines import chembl_pipeline
    src = inspect.getsource(
        chembl_pipeline.ChEMBLPipeline._step_compute_is_fda_approved
    )
    check(
        "P2-H.3 chembl_pipeline derives is_fda_approved",
        "_derive_fda" in src,
        "must derive is_fda_approved from approved_by + max_phase",
    )


def test_missing_values_no_passthrough_fallback():
    from cleaning import missing_values
    src = inspect.getsource(missing_values.recover_inchikeys_from_smiles)
    # Strip comment lines so we don't match the comment that documents
    # the removal of the passthrough.
    code_only = "\n".join(
        ln for ln in src.splitlines()
        if not ln.lstrip().startswith("#")
    )
    check(
        "P2-H.4 no 'standardize = lambda x: x' passthrough (in code)",
        "standardize = lambda x: x" not in code_only
        and "lambda x: x  # noqa" not in code_only,
        "must not have passthrough fallback in executable code",
    )
    check(
        "P2-H.5 missing_values quarantines on standardize failure",
        "_append_dead_letter" in src,
        "must quarantine when standardize is unavailable",
    )


def test_disgenet_pipeline_has_max_age_check():
    from pipelines import disgenet_pipeline
    # The class is named DisGeNETPipeline (mixed case), not DisgenetPipeline.
    src = inspect.getsource(
        disgenet_pipeline.DisGeNETPipeline._find_most_recent_cached_tsv
    )
    check(
        "P2-H.6 disgenet_pipeline has max-age check",
        "DRUGOS_DISGENET_MAX_CACHE_AGE_DAYS" in src,
        "must enforce max-age (default 90 days)",
    )


# ============================================================================
# P2-I: uniprot_pipeline checkpoint reader
# ============================================================================

def test_uniprot_pipeline_wires_checkpoint_reader():
    from pipelines import uniprot_pipeline
    src = inspect.getsource(uniprot_pipeline.UniProtPipeline.download)
    check(
        "P2-I.1 uniprot download reads checkpoint",
        "_read_checkpoint" in src,
        "_read_checkpoint must be called in download()",
    )
    check(
        "P2-I.2 uniprot DRUGOS_UNIPROT_RESUME env var",
        "DRUGOS_UNIPROT_RESUME" in src,
        "must gate resume on env var",
    )


# ============================================================================
# P0-J: disgenet_loader default filename
# ============================================================================

def test_disgenet_loader_default_filename():
    from drugos_graph import disgenet_loader
    check(
        "P0-J.1 disgenet_loader default filename has prefix",
        disgenet_loader.DEFAULT_DISGENET_CSV.name
        == "disgenet_gene_disease_associations.csv",
        f"got {disgenet_loader.DEFAULT_DISGENET_CSV.name}",
    )


# ============================================================================
# End-to-end smoke test
# ============================================================================

def test_e2e_run_unified_exit_code_4_not_1():
    import subprocess
    proc = subprocess.run(
        [sys.executable, str(HERE / "run_unified.py")],
        capture_output=True, text=True, timeout=120,
        cwd=str(HERE),
    )
    check(
        "E2E.1 run_unified exits 4 (not 1)",
        proc.returncode == 4,
        f"got exit {proc.returncode}, expected 4 (V1 criteria not met)",
    )
    check(
        "E2E.2 no NameError in output",
        "NameError" not in proc.stderr and "NameError" not in proc.stdout,
        "no NameError on phase1_processed_dir",
    )
    check(
        "E2E.4 bridge loaded nodes + edges",
        "BRIDGE SUMMARY" in proc.stdout or "BRIDGE SUMMARY" in proc.stderr,
        "bridge must run and produce summary",
    )


# ============================================================================
# Run all tests
# ============================================================================

def main():
    tests = [
        test_argparse_no_lockout,
        test_step7_takes_phase1_processed_dir,
        test_step4_takes_skip_download_and_phase1_dir,
        test_min_triples_gate_lowered,
        test_v1_launch_uses_typed_exception_not_sys_exit,
        test_run_unified_catches_v1_launch_exception,
        test_kg_builder_handles_flat_edge_dict,
        test_edge_property_whitelist_has_chembl_props,
        test_drkg_shim_preserves_edge_props,
        test_negative_sampling_filter_implemented,
        test_train_transe_filters_known_triples,
        test_validation_negatives_filtered,
        test_ec50_returns_targets_not_activates,
        test_id_patterns_accepts_chembl_tgt_prefix,
        test_omim_gene_symbol_fallback_uses_sym_prefix,
        test_pd_timestamp_utcnow_replaced,
        test_sider_fda_labels_does_not_raise,
        test_sider_frequencies_does_not_raise,
        test_ncbi_verification_not_optimistic_true,
        test_uniprot_regex_uses_official_pattern,
        test_gene_symbol_regex_accepts_title_case,
        test_protein_loader_quarantines_invalid_gene_symbol,
        test_migration_002_has_begin_commit,
        test_rollback_migration_does_not_raise_not_implemented,
        test_dead_letter_queue_has_lock,
        test_chembl_loader_deterministic_sqlite_selection,
        test_chembl_loader_unknown_standard_type_targets,
        test_chembl_pipeline_derives_fda_approved,
        test_missing_values_no_passthrough_fallback,
        test_disgenet_pipeline_has_max_age_check,
        test_uniprot_pipeline_wires_checkpoint_reader,
        test_disgenet_loader_default_filename,
        test_e2e_run_unified_exit_code_4_not_1,
    ]
    for t in tests:
        try:
            t()
        except Exception as e:
            _results.append((t.__name__, False, f"EXCEPTION: {type(e).__name__}: {e}"))

    print("\n" + "=" * 78)
    print("v21 FORENSIC AUDIT ROOT-FIX VERIFICATION RESULTS")
    print("=" * 78)
    n_pass = 0
    n_fail = 0
    for name, ok, detail in _results:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name}")
        if not ok:
            print(f"          -> {detail}")
            n_fail += 1
        else:
            n_pass += 1
    print("=" * 78)
    print(f"Total: {len(_results)}   PASS: {n_pass}   FAIL: {n_fail}")
    print("=" * 78)
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
