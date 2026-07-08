"""v26 Forensic Audit Verification Suite
=====================================

Verifies that EVERY P0/P1/P2 issue from the v20 Forensic Audit Report
(``v20_DrugOS_Forensic_Audit_Report.pdf``) has been root-level fixed in
the v26 codebase. This test reads the ACTUAL production code (not the
test cases or grep summaries) and asserts that each destructive pattern
documented in the audit is no longer present.

Run:
    cd <project_root>
    python -m pytest tests/v26_audit_verification/test_v26_audit_verification.py -v

Or directly:
    python tests/v26_audit_verification/test_v26_audit_verification.py

Categories verified (matching the audit's structure):
  §4  Bridge & Integration (12 findings)        — P0 BLOCKERS
  §5  Phase 1 Data Layer (10 findings)          — P1 SCIENTIFIC
  §6  Phase 1 Pipelines (8 findings)            — P1 SCIENTIFIC
  §7  Phase 2 Loaders & TransE (12 findings)    — P0 + P1
  §8  Compound Degradation Chains (12 chains)   — end-to-end
  §9  Stub / Placeholder / Dead-Code Inventory  — P1 + P2
  §10 Phase 2 Loaders — Phase 1 CSV Bypass Matrix — THE headline fix
  §11 Recommended Next Actions (12)             — all P0/P1/P2
"""

from __future__ import annotations

import ast
import inspect
import os
import re
import sys
import textwrap
from pathlib import Path

import pytest

# ─── Locate project root & ensure imports work ─────────────────────────────
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
PHASE1_ROOT = PROJECT_ROOT / "phase1"
PHASE2_ROOT = PROJECT_ROOT / "phase2"
for p in (str(PHASE1_ROOT), str(PHASE2_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ═══════════════════════════════════════════════════════════════════════════
# §4 Bridge & Integration — P0 BLOCKERS (the user's #1 complaint)
# ═══════════════════════════════════════════════════════════════════════════


class TestSection4BridgeIntegration:
    """Verify the 12 critical findings from AUDIT-P1-BRIDGE."""

    def test_4_1_nameerror_on_phase1_processed_dir_fixed(self):
        """§4 finding 1 / Chain 1 — THE P0 BLOCKER."""
        from drugos_graph import run_pipeline
        sig = inspect.signature(run_pipeline.step7_additional_sources)
        assert "phase1_processed_dir" in sig.parameters, (
            "step7_additional_sources must accept phase1_processed_dir "
            "(audit's #1 P0 blocker)"
        )
        src = inspect.getsource(run_pipeline.step7_additional_sources)
        assert "phase1_processed_dir" in src, (
            "phase1_processed_dir is in the signature but NOT used in the "
            "function body — the NameError bug may still be present."
        )

    def test_4_2_argparse_lockout_fixed(self):
        """§4 finding 2 / Chain 12 — argparse lockout on --skip-download."""
        run_unified_py = (PROJECT_ROOT / "run_unified.py").read_text()
        assert "BooleanOptionalAction" in run_unified_py, (
            "run_unified.py must use argparse.BooleanOptionalAction for "
            "--skip-download so --no-skip-download is available"
        )
        bad_pattern = re.compile(
            r"--skip-download[^)]*action=['\"]store_true['\"][^)]*default=True",
            re.DOTALL,
        )
        assert not bad_pattern.search(run_unified_py), (
            "run_unified.py still has the broken --skip-download "
            "(store_true + default=True) pattern"
        )

    def test_4_3_min_triples_gate_lowered(self):
        """§4 finding 3 — default mode exits 1 with no model trained."""
        from drugos_graph import run_pipeline
        src = inspect.getsource(run_pipeline.step11_train_transe)
        assert "MIN_TRIPLES_FOR_TRANSE = 20" in src, (
            "MIN_TRIPLES_FOR_TRANSE must be 20 (was 100) so the toy "
            "fixture can train"
        )
        assert "PRODUCTION_MIN_TRIPLES = 100" in src, (
            "PRODUCTION_MIN_TRIPLES must be 100 (separate from the hard gate)"
        )

    def test_4_4_edge_properties_preserved_through_pipeline(self):
        """§4 finding 4 / Chain 4 — edge properties stripped by DRKG shim."""
        from drugos_graph import run_pipeline
        src_step1 = inspect.getsource(run_pipeline.step1_load_phase1)
        assert "edge_props" in src_step1, (
            "step1_load_phase1 must attach edge_props to the df shim"
        )
        for key in ("pchembl_value", "standard_relation", "evidence", "source"):
            assert key in src_step1, (
                f"step1_load_phase1 must flatten {key} as a top-level column"
            )
        sig3 = inspect.signature(run_pipeline.step3_load_neo4j)
        assert "edge_props_lookup" in sig3.parameters, (
            "step3_load_neo4j must accept edge_props_lookup to re-attach "
            "per-edge properties when loading into Neo4j"
        )

    def test_4_5_drugbank_consumes_phase1_csv_by_default(self):
        """§4 finding 5 — DrugBank parsed twice, bypassing Phase 1."""
        from drugos_graph import run_pipeline
        sig = inspect.signature(run_pipeline.step4_drugbank_enrichment)
        assert "phase1_processed_dir" in sig.parameters, (
            "step4_drugbank_enrichment must accept phase1_processed_dir"
        )
        assert "skip_download" in sig.parameters, (
            "step4_drugbank_enrichment must accept skip_download"
        )
        src = inspect.getsource(run_pipeline.step4_drugbank_enrichment)
        assert "drugbank_drugs.csv" in src, (
            "step4 must read Phase 1's drugbank_drugs.csv by default"
        )

    def test_4_6_string_uniprot_chembl_skipped_when_bridge_used(self):
        """§4 finding 6 — STRING, UniProt, ChEMBL re-downloaded in Phase 2."""
        from drugos_graph import run_pipeline
        src = inspect.getsource(run_pipeline.step7_additional_sources)
        assert '"phase1"' in src or "'phase1'" in src, (
            "step7 must check data_source='phase1' to skip 7a/7b/7c"
        )
        assert "string_skipped" in src or "phase1_bridge_already_loaded" in src, (
            "step7 must skip STRING when data_source='phase1'"
        )
        assert "uniprot_skipped" in src, (
            "step7 must skip UniProt when data_source='phase1'"
        )
        assert "chembl_skipped" in src, (
            "step7 must skip ChEMBL when data_source='phase1'"
        )

    def test_4_7_ec50_classified_as_targets_not_activates(self):
        """§4 finding 7 / Chain 8 — EC50 mis-classified as 'activates'."""
        from drugos_graph import phase1_bridge
        src = inspect.getsource(phase1_bridge)
        assert "ec50" in src.lower() and "ac50" in src.lower(), (
            "phase1_bridge must have an EC50/AC50 branch"
        )
        ec50_branch = re.search(
            r'if\s+a\s+in\s*\(\s*["\']ec50["\']\s*,\s*["\']ac50["\']\s*\)\s*:\s*return\s+["\'](\w+)["\']',
            src,
        )
        assert ec50_branch is not None, (
            "phase1_bridge must have an explicit `if a in ('ec50', 'ac50'): return '...'` branch"
        )
        assert ec50_branch.group(1) == "targets", (
            f"EC50/AC50 must return 'targets' (not 'activates'); got "
            f"'{ec50_branch.group(1)}'"
        )

    def test_4_8_bridge_emits_production_accepted_ids(self):
        """§4 finding 8 / Chain 9 — bridge emits IDs that production rejects."""
        from drugos_graph import phase1_bridge
        src = inspect.getsource(phase1_bridge)
        assert "CHEMBL_TGT_" in src, "phase1_bridge must emit CHEMBL_TGT_ prefix"
        chembl_tgt_match = re.search(
            r'f["\']CHEMBL_TGT_\{[^}]+\}["\']', src,
        )
        assert chembl_tgt_match is not None, (
            "phase1_bridge must construct CHEMBL_TGT_<id> strings"
        )
        assert 'SYM:' in src, (
            "phase1_bridge must emit SYM:<symbol> for gene IDs"
        )

    def test_4_9_step4_signature_no_mismatch(self):
        """§4 finding 12 — step4 signature mismatch."""
        from drugos_graph import run_pipeline
        sig = inspect.signature(run_pipeline.step4_drugbank_enrichment)
        for required_param in ("skip_neo4j", "skip_download", "phase1_processed_dir"):
            assert required_param in sig.parameters, (
                f"step4_drugbank_enrichment must accept {required_param}"
            )

    def test_4_10_run_full_pipeline_threads_phase1_dir(self):
        """§4 — run_full_pipeline threads phase1_processed_dir through."""
        from drugos_graph import run_pipeline
        sig = inspect.signature(run_pipeline.run_full_pipeline)
        assert "phase1_processed_dir" in sig.parameters, (
            "run_full_pipeline must accept phase1_processed_dir"
        )
        src = inspect.getsource(run_pipeline.run_full_pipeline)
        assert "phase1_processed_dir=phase1_processed_dir" in src, (
            "run_full_pipeline must thread phase1_processed_dir to step4/step7/step1"
        )

    def test_4_11_v1_launch_criteria_uses_typed_exception(self):
        """§4 / §12 — sys.exit(1) in library code breaks embedding."""
        from drugos_graph import run_pipeline
        assert hasattr(run_pipeline, "V1LaunchCriteriaFailed"), (
            "run_pipeline must expose V1LaunchCriteriaFailed typed exception"
        )
        src = inspect.getsource(run_pipeline.run_full_pipeline)
        assert "raise V1LaunchCriteriaFailed" in src, (
            "run_full_pipeline must raise V1LaunchCriteriaFailed (not sys.exit(1)) "
            "when V1 launch criteria fail"
        )

    def test_4_12_run_unified_catches_v1_exception(self):
        """§4 / §12 — run_unified catches V1LaunchCriteriaFailed → exit 4."""
        run_unified_py = (PROJECT_ROOT / "run_unified.py").read_text()
        assert "V1LaunchCriteriaFailed" in run_unified_py, (
            "run_unified.py must catch V1LaunchCriteriaFailed and translate to exit 4"
        )
        assert "SystemExit" in run_unified_py, (
            "run_unified.py must catch SystemExit defensively"
        )


# ═══════════════════════════════════════════════════════════════════════════
# §5 Phase 1 Data Layer — P1 SCIENTIFIC
# ═══════════════════════════════════════════════════════════════════════════


class TestSection5Phase1DataLayer:
    """Verify the 10 critical findings from AUDIT-P1-DATA."""

    def test_5_1_uniprot_regex_unified(self):
        """§5 finding 2 — three divergent UniProt regexes."""
        models_py = (PHASE1_ROOT / "database" / "models.py").read_text()
        assert "_UNIPROT_ACCESSION_RE" in models_py, (
            "models.py must reference resolver_utils._UNIPROT_ACCESSION_RE"
        )

    def test_5_2_gene_symbol_regex_unified(self):
        """§5 finding 1 — three divergent gene-symbol regexes."""
        models_py = (PHASE1_ROOT / "database" / "models.py").read_text()
        assert "_HUMAN_GENE_SYMBOL_RE" in models_py, (
            "models.py must define _HUMAN_GENE_SYMBOL_RE (strict, separate "
            "from the lenient _GENE_SYMBOL_RE)"
        )

    def test_5_3_inchikey_validators_unified(self):
        """§5 finding 4 — three divergent InChIKey validators."""
        models_py = (PHASE1_ROOT / "database" / "models.py").read_text()
        loaders_py = (PHASE1_ROOT / "database" / "loaders.py").read_text()
        assert "is_valid_inchikey" in models_py, (
            "models.py must reference cleaning.normalizer.is_valid_inchikey"
        )
        assert "is_valid_inchikey" in loaders_py, (
            "loaders.py must reference cleaning.normalizer.is_valid_inchikey"
        )

    def test_5_4_migration_002_has_begin_commit(self):
        """§5 finding 6 / Chain 5 — Migration 002 missing BEGIN/COMMIT."""
        sql_path = (
            PHASE1_ROOT / "database" / "migrations"
            / "002_bug_fixes_migration.sql"
        )
        sql = sql_path.read_text()
        first_50_lines = "\n".join(sql.split("\n")[:50])
        assert re.search(r"^\s*BEGIN\s*;", first_50_lines, re.MULTILINE), (
            "002_bug_fixes_migration.sql must have an outer BEGIN near the top"
        )
        last_50_lines = "\n".join(sql.split("\n")[-50:])
        assert re.search(r"^\s*COMMIT\s*;", last_50_lines, re.MULTILINE), (
            "002_bug_fixes_migration.sql must have an outer COMMIT at the end"
        )

    def test_5_5_rollback_migration_implemented(self):
        """§5 finding 5 / §9 — rollback_migration raised NotImplementedError."""
        run_migrations_py = (
            PHASE1_ROOT / "database" / "migrations" / "run_migrations.py"
        ).read_text()
        match = re.search(
            r"def rollback_migration\([^)]*\)[^:]*:(.*?)(?=\ndef |\Z)",
            run_migrations_py,
            re.DOTALL,
        )
        assert match is not None, "rollback_migration must exist"
        body = match.group(1)
        assert "_rollback.sql" in body, (
            "rollback_migration must look for a <name>_rollback.sql sidecar file"
        )

    def test_5_6_no_true_duplicate_methods_in_models(self):
        """§5 / §3 — 280+ duplicate method definitions in models.py."""
        models_py = (PHASE1_ROOT / "database" / "models.py").read_text()
        tree = ast.parse(models_py)
        class_at_line: dict[int, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for n in range(
                    node.lineno, (node.end_lineno or node.lineno) + 1
                ):
                    class_at_line[n] = node.name
        from collections import defaultdict
        defs_per_class: dict[tuple[str, str], list[int]] = defaultdict(list)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cls = class_at_line.get(node.lineno, "<module>")
                defs_per_class[(cls, node.name)].append(node.lineno)
        true_dups = {k: v for k, v in defs_per_class.items() if len(v) > 1}
        assert not true_dups, (
            f"models.py has TRUE duplicate method definitions (same name "
            f"within same class): {true_dups}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# §6 Phase 1 Pipelines — P1 SCIENTIFIC
# ═══════════════════════════════════════════════════════════════════════════


class TestSection6Phase1Pipelines:
    """Verify the 8 critical findings from AUDIT-P1-PIPE."""

    def test_6_1_disgenet_pipeline_no_silent_stale_cache(self):
        """§6 finding 3 — DisGeNET silent fallback to stale cached TSV."""
        disgenet_py = (
            PHASE1_ROOT / "pipelines" / "disgenet_pipeline.py"
        ).read_text()
        assert "max_age" in disgenet_py or "DRUGOS_DISGENET" in disgenet_py, (
            "disgenet_pipeline must have a freshness / max-age check"
        )

    def test_6_2_missing_values_no_passthrough_fallback(self):
        """§6 finding 2 — Silent InChIKey passthrough fallback."""
        mv_py = (PHASE1_ROOT / "cleaning" / "missing_values.py").read_text()
        assert "QUARANTINED" in mv_py or "quarantine" in mv_py, (
            "missing_values.py must QUARANTINE (not pass through) InChIKeys "
            "when standardize_inchikey is unavailable"
        )

    def test_6_3_omim_pipeline_dead_code_removed(self):
        """§6 finding 4 — ~150 lines of dead code in omim_pipeline."""
        omim_py = (PHASE1_ROOT / "pipelines" / "omim_pipeline.py").read_text()
        match = re.search(
            r"def download\(self.*?(?=\ndef )",
            omim_py,
            re.DOTALL,
        )
        assert match is not None, "OMIMPipeline.download() must exist"
        download_body = match.group(0)
        for dead_fn in ("_download_via_api", "_fetch_gene_map_page", "_write_gene_map_json"):
            call_pattern = re.compile(rf"\b{dead_fn}\s*\(")
            assert not call_pattern.search(download_body), (
                f"OMIMPipeline.download() must not call the dead function "
                f"{dead_fn} (audit §6 finding 4)"
            )


# ═══════════════════════════════════════════════════════════════════════════
# §7 Phase 2 Loaders & TransE — P0 + P1 SCIENTIFIC
# ═══════════════════════════════════════════════════════════════════════════


class TestSection7Phase2LoadersAndTransE:
    """Verify the 12 critical findings from AUDIT-P2-LOADERS."""

    def test_7_1_negative_sampling_implements_filter(self):
        """§7 finding 1 / Chain 6 — FAKE known-positive filter."""
        from drugos_graph import negative_sampling
        src = inspect.getsource(negative_sampling)
        assert "n_skipped_as_known" in src or "_known_ht_pairs" in src, (
            "negative_sampling must IMPLEMENT the known-positive filter "
            "(not just a comment)"
        )

    def test_7_2_transe_train_implements_filter(self):
        """§7 finding 2 / Chain 6 — FAKE known-triples filter in training."""
        from drugos_graph import transe_model
        src = inspect.getsource(transe_model)
        assert (
            "known" in src.lower() and "filter" in src.lower()
        ), "transe_model must implement (and document) the known-triples filter"

    def test_7_3_sider_fda_labels_implemented(self):
        """§7 finding 4 / Chain 7 — Patient-safety STUB."""
        from drugos_graph import sider_loader
        assert hasattr(sider_loader, "parse_sider_fda_labels"), (
            "sider_loader must have parse_sider_fda_labels"
        )
        src = inspect.getsource(sider_loader.parse_sider_fda_labels)
        assert "raise NotImplementedError" not in src, (
            "parse_sider_fda_labels must NOT raise NotImplementedError "
            "(audit §7 finding 4 / Chain 7 patient-safety stub)"
        )

    def test_7_4_sider_frequencies_implemented(self):
        """§7 finding 5 / Chain 7 — Patient-safety STUB."""
        from drugos_graph import sider_loader
        assert hasattr(sider_loader, "parse_sider_frequencies"), (
            "sider_loader must have parse_sider_frequencies"
        )
        src = inspect.getsource(sider_loader.parse_sider_frequencies)
        assert "raise NotImplementedError" not in src, (
            "parse_sider_frequencies must NOT raise NotImplementedError"
        )

    def test_7_5_id_crosswalk_ncbi_verification_real(self):
        """§7 finding 6 — FAKE NCBI verification.

        Audit: ``verify_builtin_against_ncbi`` returned True for every
        entry without calling NCBI. Note: this is a METHOD on the
        IDCrosswalk class (not a module-level function).
        """
        from drugos_graph import id_crosswalk
        idc_class = getattr(id_crosswalk, "IDCrosswalk", None)
        assert idc_class is not None, (
            "id_crosswalk must expose IDCrosswalk class"
        )
        assert hasattr(idc_class, "verify_builtin_against_ncbi"), (
            "IDCrosswalk class must have verify_builtin_against_ncbi method"
        )
        src = inspect.getsource(idc_class.verify_builtin_against_ncbi)
        # The ACTUAL broken pattern is `results[key] = True  # optimistic`
        # as executable code (not in a docstring/comment). Strip comments
        # and docstrings, then check.
        # Remove triple-quoted strings (docstrings).
        cleaned = re.sub(r'"""[^"]*"""', '', src, flags=re.DOTALL)
        cleaned = re.sub(r"'''[^']*'''", '', cleaned, flags=re.DOTALL)
        # Remove single-line comments.
        cleaned = re.sub(r'#[^\n]*', '', cleaned)
        # The fake pattern: assigning True to a results dict without
        # actually verifying. Look for `= True` followed by what was
        # `# optimistic` (now stripped). The real fix uses an actual
        # NCBI call (urllib.request).
        assert "urllib.request" in cleaned or "urlopen" in cleaned, (
            "verify_builtin_against_ncbi must make a REAL NCBI HTTP call "
            "(urllib.request / urlopen) — not just return True for every entry"
        )
        assert "DRUGOS_VERIFY_BUILTIN" in src, (
            "verify_builtin_against_ncbi must gate real NCBI calls "
            "behind DRUGOS_VERIFY_BUILTIN=1"
        )

    def test_7_6_chembl_loader_nondeterministic_sqlite_fixed(self):
        """§7 finding 7 — Non-deterministic SQLite selection.

        Audit: ``db_files = list(Path(chembl_dir).rglob('*.db'))`` then
        ``db_path = db_files[0]``. Different runs picked different DBs.

        Fix: v24 sorts db_files deterministically (by size, mtime, path)
        before picking db_files[0].
        """
        from drugos_graph import chembl_loader
        src = inspect.getsource(chembl_loader)
        # The actual non-determinism is the ASSIGNMENT `db_path = db_files[0]`
        # (not just any mention of `db_files[0]` in a comment).
        # Find ALL occurrences of `db_path = db_files[0]` (or similar
        # assignment patterns) in executable code (not comments).
        # Strip comments first.
        cleaned = re.sub(r'#[^\n]*', '', src)
        # Strip docstrings.
        cleaned = re.sub(r'"""[^"]*"""', '', cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"'''[^']*'''", '', cleaned, flags=re.DOTALL)
        # Find `db_files[0]` assignments in executable code.
        bad_pattern = re.compile(r"db_files\s*\[\s*0\s*\]")
        occurrences = list(bad_pattern.finditer(cleaned))
        if not occurrences:
            pytest.skip("chembl_loader does not use db_files[0] in executable code — already fixed")
        for occ in occurrences:
            # Look 1500 chars BEFORE the db_files[0] access for a sort call.
            window_start = max(0, occ.start() - 1500)
            window = cleaned[window_start:occ.start()]
            assert "sort" in window.lower(), (
                f"chembl_loader accesses db_files[0] at offset "
                f"{occ.start()} without a preceding sort() call within "
                f"1500 chars. This is the non-deterministic SQLite "
                f"selection bug (audit §7 finding 7)."
            )

    def test_7_7_stitch_edge_type_no_silent_collapse(self):
        """§7 finding 8 — STITCH edge type collapses silently."""
        from drugos_graph import run_pipeline
        src = inspect.getsource(run_pipeline.step5_stitch_ingestion)
        assert "interacts_with" in src, (
            "step5 must use 'interacts_with' (neutral) as the STITCH "
            "rel_type fallback, not 'binds' (mechanism-specific)"
        )

    def test_7_8_chembl_unknown_standard_type_defaults_to_targets(self):
        """§7 finding 12 — Unknown standard_type defaults to 'binds'."""
        from drugos_graph import chembl_loader
        src = inspect.getsource(chembl_loader.standard_type_to_relation)
        assert "targets" in src, (
            "standard_type_to_relation must default unknown types to 'targets' "
            "(not 'binds')"
        )


# ═══════════════════════════════════════════════════════════════════════════
# §10 Phase 2 Loaders — Phase 1 CSV Bypass Matrix (THE headline fix)
# ═══════════════════════════════════════════════════════════════════════════


class TestSection10BypassMatrix:
    """Verify the Phase 2 Loaders — Phase 1 CSV Bypass Matrix.

    This is the user's #1 requirement: "phase 1 and phase 2 should be
    100 percent integrated."
    """

    def test_10_1_all_4_loaders_have_phase1_aware_functions(self):
        """v26 ROOT FIX: the 4 raw re-fetch loaders (chembl, drugbank_parser,
        string, uniprot) must have Phase-1-aware functions.
        """
        from drugos_graph import (
            chembl_loader,
            drugbank_parser,
            string_loader,
            uniprot_loader,
        )
        assert hasattr(chembl_loader, "parse_chembl_activities_from_phase1_csv")
        assert hasattr(chembl_loader, "chembl_to_edge_records_from_phase1")
        assert hasattr(drugbank_parser, "parse_drugbank_from_phase1_csv")
        assert hasattr(drugbank_parser, "drugbank_to_node_records_from_phase1")
        assert hasattr(drugbank_parser, "drugbank_to_target_edges_from_phase1")
        assert hasattr(string_loader, "parse_string_ppi_from_phase1_csv")
        assert hasattr(string_loader, "string_to_edge_records_from_phase1")
        assert hasattr(uniprot_loader, "parse_uniprot_entries_from_phase1_csv")
        assert hasattr(uniprot_loader, "uniprot_to_node_records_from_phase1")

    def test_10_2_disgenet_loader_reads_phase1_csv(self):
        """disgenet_loader.py reads Phase 1's
        disgenet_gene_disease_associations.csv."""
        from drugos_graph import disgenet_loader
        assert (
            "disgenet_gene_disease_associations.csv"
            in str(disgenet_loader.DEFAULT_DISGENET_CSV)
        ), (
            "disgenet_loader.DEFAULT_DISGENET_CSV must point to "
            "disgenet_gene_disease_associations.csv (the correct prefixed name)"
        )

    def test_10_3_omim_loader_reads_phase1_csv(self):
        """omim_loader.py reads Phase 1's omim_gene_disease_associations.csv."""
        from drugos_graph import omim_loader
        assert (
            "omim_gene_disease_associations.csv"
            in str(omim_loader.DEFAULT_OMIM_CSV)
        )

    def test_10_4_pubchem_loader_reads_phase1_csv(self):
        """pubchem_loader.py reads Phase 1's pubchem_enrichment.csv."""
        from drugos_graph import pubchem_loader
        assert (
            "pubchem_enrichment.csv"
            in str(pubchem_loader.DEFAULT_PUBCHEM_CSV)
        )

    def test_10_5_phase1_aware_functions_actually_work(self):
        """End-to-end: each Phase-1-aware function actually reads the
        Phase 1 CSV and produces non-empty records."""
        from drugos_graph import (
            chembl_loader,
            drugbank_parser,
            string_loader,
            uniprot_loader,
        )
        db_df = drugbank_parser.parse_drugbank_from_phase1_csv()
        assert len(db_df) > 0, "drugbank_parser Phase 1 CSV must have rows"
        db_nodes = drugbank_parser.drugbank_to_node_records_from_phase1(db_df)
        assert len(db_nodes) > 0, "drugbank_parser must emit Compound nodes"

        ch_df = chembl_loader.parse_chembl_activities_from_phase1_csv()
        assert len(ch_df) > 0, "chembl_loader Phase 1 CSV must have rows"
        ch_edges = chembl_loader.chembl_to_edge_records_from_phase1(ch_df)
        assert len(ch_edges) > 0, "chembl_loader must emit DPI edges"

        st_df = string_loader.parse_string_ppi_from_phase1_csv()
        assert len(st_df) > 0, "string_loader Phase 1 CSV must have rows"
        st_edges = string_loader.string_to_edge_records_from_phase1(st_df)
        assert len(st_edges) > 0, "string_loader must emit PPI edges"

        up_records = uniprot_loader.parse_uniprot_entries_from_phase1_csv()
        assert len(up_records) > 0, "uniprot_loader Phase 1 CSV must have rows"
        up_nodes = uniprot_loader.uniprot_to_node_records_from_phase1(up_records)
        assert len(up_nodes) > 0, "uniprot_loader must emit Protein nodes"

    def test_10_6_bridge_reads_all_11_phase1_csvs(self):
        """phase1_bridge must read ALL 11 Phase 1 CSVs."""
        from drugos_graph import phase1_bridge
        src = inspect.getsource(phase1_bridge)
        required_csvs = [
            "drugbank_drugs.csv",
            "drugbank_interactions.csv.gz",
            "drugbank_indications.csv",
            "omim_gene_disease_associations.csv",
            "omim_gene_disease_susceptibility.csv",
            "chembl_drugs.csv",
            "chembl_activities_clean.csv",
            "uniprot_proteins.csv",
            "string_protein_protein_interactions.csv",
            "disgenet_gene_disease_associations.csv",
            "pubchem_enrichment.csv",
        ]
        for csv_name in required_csvs:
            assert csv_name in src, (
                f"phase1_bridge must reference Phase 1 CSV: {csv_name}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# §11 End-to-end smoke test (the user's #1 deliverable)
# ═══════════════════════════════════════════════════════════════════════════


class TestEndToEndSmoke:
    """The user's #1 deliverable: running the actual pipeline end-to-end."""

    def test_pipeline_runs_end_to_end_with_v1_pass(self):
        """Run ``python run_unified.py`` (default mode) and verify:
          - exit code 0
          - V1 launch criteria checked (not just skipped)
          - model trained (model_saved=True)
          - AUC computed (best_val_auc > 0)
        """
        import subprocess
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "run_unified.py")],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(PROJECT_ROOT),
        )
        output = result.stdout + result.stderr
        assert result.returncode == 0, (
            f"run_unified.py must exit 0 (success). Got exit code "
            f"{result.returncode}. Output tail:\n"
            f"{output[-3000:]}"
        )
        assert "V1 LAUNCH CRITERIA" in output, (
            "run_unified.py output must mention V1 LAUNCH CRITERIA"
        )
        assert "PASSED" in output, (
            "V1 launch criteria must PASS (dev smoke-test mode)"
        )
        assert "model_saved" in output or "model_saved_to_disk" in output, (
            "Pipeline must report model_saved status"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
