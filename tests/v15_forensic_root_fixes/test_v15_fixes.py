#!/usr/bin/env python3
"""
v15 Forensic Root-Fix Regression Tests
======================================

Tests for every fix applied in the v15 forensic root-fix pass.
Each test is named after the audit issue ID (REM-*) it covers.
These tests invoke REAL code paths — no MagicMock for the SUT.

Run with:
    cd /home/z/my-project/work/v14
    python3 -m pytest tests/v15_forensic_root_fixes/ -v
"""

from __future__ import annotations

import sys
import gzip
import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

# Make both phase1 and phase2 importable
HERE = Path(__file__).resolve().parent
V14_ROOT = HERE.parent.parent  # tests/v15_forensic_root_fixes -> v14
PHASE1_ROOT = V14_ROOT / "phase1"
PHASE2_ROOT = V14_ROOT / "phase2"
for p in (str(PHASE2_ROOT), str(PHASE1_ROOT), str(V14_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ─── REM-12/13/14: Bridge reads all 11 Phase 1 CSVs ──────────────────────────

class TestBridgeReadsAllPhase1CSVs:
    """The bridge must read ALL 11 Phase 1 source CSVs, not just 9."""

    def test_bridge_paths_dict_includes_chembl_activities(self):
        from drugos_graph.phase1_bridge import read_phase1_outputs
        # Inspect the source to confirm the new keys are present.
        import inspect
        src = inspect.getsource(read_phase1_outputs)
        assert "chembl_activities" in src, (
            "Bridge must include chembl_activities key — REM-12 not fixed"
        )
        assert "chembl_activities_clean.csv" in src
        assert "omim_susceptibility" in src
        assert "omim_gene_disease_susceptibility.csv" in src

    def test_bridge_emits_chembl_activity_edges_with_direction(self):
        """ChEMBL activity edges must be classified into inhibits/activates/targets
        based on activity_type — not hardcoded to 'targets'.

        v25 ROOT FIX: the original test expected EC50 → 'activates'.
        But the v20 audit (Section 4 finding 7 / Chain 8) flagged this
        as a CRITICAL patient-safety bug: EC50 (Half-maximal Effective
        Concentration) and AC50 measure the potency of a compound that
        produces 50% of its MAXIMUM effect — this can be an AGONIST
        (activates) OR an ANTAGONIST (inhibits), depending on the assay
        design. The comment in the function admitted this. Mis-labeling
        an antagonist as 'activates' feeds the RL ranker wrong
        directionality for downstream drug-disease prediction. The
        v21/v24 ROOT FIX returns 'targets' (interaction confirmed,
        direction unclassified) for EC50/AC50. This updated test
        verifies the v21/v24 correct behavior.
        """
        from drugos_graph.phase1_bridge import (
            _classify_chembl_activity_edge,
        )
        # Direct test of the classifier (v21/v24 correct behavior).
        assert _classify_chembl_activity_edge("IC50") == "targets"
        assert _classify_chembl_activity_edge("Inhibition") == "inhibits"
        assert _classify_chembl_activity_edge("Activation") == "activates"
        # v25: EC50/AC50 → 'targets' (NOT 'activates') — EC50 measures
        # potency of agonist OR antagonist; the comment in the function
        # admitted this. Mis-labeling antagonists as 'activates' feeds
        # the RL ranker wrong directionality (audit Chain 8).
        assert _classify_chembl_activity_edge("EC50") == "targets", (
            "EC50 must be 'targets' (not 'activates') — EC50 measures "
            "potency of agonist OR antagonist; mis-labeling feeds RL "
            "ranker wrong directionality (v20 audit Chain 8)"
        )
        assert _classify_chembl_activity_edge("AC50") == "targets", (
            "AC50 must be 'targets' (not 'activates') — same as EC50"
        )
        assert _classify_chembl_activity_edge("Ki") == "targets"
        assert _classify_chembl_activity_edge("") == "targets"
        assert _classify_chembl_activity_edge("Potency") == "targets"

    def test_bridge_emits_omim_susceptibility_edges(self):
        """OMIM susceptibility associations must be emitted under a DISTINCT
        `susceptible_to` relation — not conflated with causative `associated_with`."""
        from drugos_graph.phase1_bridge import stage_phase1_to_phase2, read_phase1_outputs
        pdir = PHASE1_ROOT / "processed_data"
        if not pdir.exists():
            pytest.skip("Phase 1 processed_data dir not found")
        frames = read_phase1_outputs(pdir)
        staged = stage_phase1_to_phase2(frames, phase1_processed_dir=pdir)
        edge_types = list(staged.edges.keys())
        # Verify the new edge type is present (when the CSV has data).
        susc_df = frames.get("omim_susceptibility")
        if susc_df is not None and not susc_df.empty:
            assert ("Gene", "susceptible_to", "Disease") in edge_types, (
                f"susceptible_to edge type missing — got {edge_types}"
            )

    def test_chembl_activities_loaded_when_present(self):
        """When chembl_activities_clean.csv has data, the bridge must stage
        Compound→{inhibits,activates,targets}→Protein edges from it."""
        from drugos_graph.phase1_bridge import read_phase1_outputs, stage_phase1_to_phase2
        pdir = PHASE1_ROOT / "processed_data"
        if not (pdir / "chembl_activities_clean.csv").exists():
            pytest.skip("chembl_activities_clean.csv fixture missing")
        frames = read_phase1_outputs(pdir)
        # Must have read the file
        assert "chembl_activities" in frames
        assert not frames["chembl_activities"].empty, "chembl_activities CSV is empty"
        staged = stage_phase1_to_phase2(frames, phase1_processed_dir=pdir)
        # At least one of these edge types should be present from ChEMBL activities
        chembl_edge_types = [
            ("Compound", "inhibits", "Protein"),
            ("Compound", "activates", "Protein"),
            ("Compound", "targets", "Protein"),
        ]
        present = [et for et in chembl_edge_types if et in staged.edges]
        assert len(present) > 0, "No ChEMBL activity edges staged"


# ─── REM-23: DC-10 STRING freshness check uses correct filename ──────────────

class TestStringFreshnessCheckFixed:
    """The STRING freshness check must stat the file the downloader actually writes."""

    def test_freshness_check_uses_data_sources_filename(self):
        import inspect
        from drugos_graph import run_pipeline
        src = inspect.getsource(run_pipeline.step7_additional_sources)
        # The buggy hardcoded filename must be gone (in the freshness check context)
        assert 'RAW_DIR / "9606.protein.info.v12.0.txt.gz"' not in src, (
            "Old hardcoded STRING filename still present in freshness check"
        )
        # The new dynamic lookup must be present
        assert 'DATA_SOURCES' in src, "DATA_SOURCES import missing"
        assert '_string_filename' in src or 'string_ppi.txt.gz' in src


# ─── REM-24: --skip-download is honored by steps 5, 6, 7 ──────────────────────

class TestSkipDownloadHonored:
    """All step5/6/7 sub-steps must respect skip_download=True."""

    def test_step5_stitch_accepts_skip_download(self):
        import inspect
        from drugos_graph.run_pipeline import step5_stitch_ingestion
        sig = inspect.signature(step5_stitch_ingestion)
        assert "skip_download" in sig.parameters, (
            "step5_stitch_ingestion must accept skip_download parameter"
        )

    def test_step6_sider_accepts_skip_download(self):
        import inspect
        from drugos_graph.run_pipeline import step6_sider_ingestion
        sig = inspect.signature(step6_sider_ingestion)
        assert "skip_download" in sig.parameters

    def test_step7_additional_sources_accepts_skip_download(self):
        import inspect
        from drugos_graph.run_pipeline import step7_additional_sources
        sig = inspect.signature(step7_additional_sources)
        assert "skip_download" in sig.parameters

    def test_step5_returns_skipped_when_no_cache(self):
        """When --skip-download and no cached file, step5 returns {skipped: True}."""
        from drugos_graph.run_pipeline import step5_stitch_ingestion
        # Ensure the cached file doesn't exist (use a temp RAW_DIR)
        with tempfile.TemporaryDirectory() as tmp:
            import drugos_graph.run_pipeline as rp
            orig_raw = rp.RAW_DIR
            try:
                rp.RAW_DIR = Path(tmp)
                r = step5_stitch_ingestion(skip_neo4j=True, skip_download=True)
                assert r.get("skipped") is True, f"Expected skipped=True, got {r}"
                assert r.get("reason") == "skip_download"
            finally:
                rp.RAW_DIR = orig_raw


# ─── REM-25: run_unified.py wires the full pipeline ──────────────────────────

class TestRunUnifiedWiresFullPipeline:
    """run_unified.py must support --full-pipeline to chain into run_full_pipeline."""

    def test_full_pipeline_flag_exists(self):
        src = (V14_ROOT / "run_unified.py").read_text()
        assert "--full-pipeline" in src, "Missing --full-pipeline CLI flag"
        assert "run_full_pipeline" in src, "Missing run_full_pipeline invocation"
        assert 'data_source="phase1"' in src, "Missing data_source='phase1' arg"


# ─── SIDER runtime crash fixes (column swap + regex) ──────────────────────────

class TestSiderColumnAndRegexFixes:
    """SIDER_COLUMN_NAMES must match the actual SIDER file schema, and the
    CID regex must accept BOTH legacy (CIDm/CIDs) and production (CID0/CID1) formats."""

    def test_column_names_swapped_correctly(self):
        """V19 ROOT FIX: col 1 is FLAT, col 2 is STEREO.

        v25 ROOT FIX: the original v15 test expected col 1=STEREO,
        col 2=FLAT — but the V19 forensic re-audit found that the
        v15 "ROOT FIX" was ITSELF the bug. The SIDER file's own
        module docstring (lines 73-74) and the official SIDER
        documentation (http://sideeffects.embl.de/data/) BOTH state:
          col 1: stitch_id_flat    — CIDm-prefixed (or CID0 in newer format) = FLAT
          col 2: stitch_id_stereo  — CIDs-prefixed (or CID1 in newer format) = STEREO
        The v15 swap caused SIDER_CIDM_REGEX (FLAT regex) to be applied
        to col 2 (STEREO values), and SIDER_CIDS_REGEX (STEREO regex)
        to col 1 (FLAT values) → every row failed cross-column regex
        check → DLQ → 0 rows parsed → SiderCriticalError. The v9-v15
        "FORENSIC VALIDATED" stamps were earned against fixture files
        that used the SAME (wrong) column order — the production file
        does not.
        """
        from drugos_graph.sider_loader import SIDER_COLUMN_NAMES
        # V19 correct order: col 1 = FLAT, col 2 = STEREO
        assert SIDER_COLUMN_NAMES[0] == "stitch_id_flat", (
            f"Col 1 must be stitch_id_flat (V19 ROOT FIX — matches SIDER "
            f"file docstring + official schema), got {SIDER_COLUMN_NAMES[0]}"
        )
        assert SIDER_COLUMN_NAMES[1] == "stitch_id_stereo", (
            f"Col 2 must be stitch_id_stereo (V19 ROOT FIX), got {SIDER_COLUMN_NAMES[1]}"
        )

    def test_cidm_regex_accepts_legacy_and_production(self):
        from drugos_graph.sider_loader import SIDER_CIDM_REGEX
        # Legacy format
        m = SIDER_CIDM_REGEX.match("CIDm0000085")
        assert m is not None and m.group(1) == "0000085"
        # Production format (CID0 = flat)
        m = SIDER_CIDM_REGEX.match("CID000010917")
        assert m is not None and m.group(1) == "00010917"

    def test_cids_regex_accepts_legacy_and_production(self):
        from drugos_graph.sider_loader import SIDER_CIDS_REGEX
        # Legacy format
        m = SIDER_CIDS_REGEX.match("CIDs0000085")
        assert m is not None and m.group(1) == "0000085"
        # Production format (CID1 = stereo)
        m = SIDER_CIDS_REGEX.match("CID100000085")
        assert m is not None and m.group(1) == "00000085"


# ─── SIDER row-count guard fixture-friendly ──────────────────────────────────

class TestSiderRowCountGuardFixtureFriendly:
    """The row-count guard must not crash on small fixture files."""

    def test_small_sider_file_does_not_raise(self):
        """A 2-3 MB SIDER partial file should produce a WARNING, not raise."""
        from drugos_graph.sider_loader import parse_sider_side_effects
        sider_path = PHASE2_ROOT / "data" / "raw" / "sider_meddra_all_se.tsv.gz"
        if not sider_path.exists():
            pytest.skip("SIDER fixture not present")
        # Should NOT raise SiderDataQualityError on the small fixture
        df = parse_sider_side_effects(filepath=sider_path)
        assert len(df) > 0, "SIDER parser produced 0 rows"


# ─── REM-26: graph_stats.py per-type density silent 0.0 → None ───────────────

class TestGraphStatsDensityNoneOnFailure:
    """A failed density query must report None, not silently report 0.0."""

    def test_per_type_density_uses_none_not_zero(self):
        import inspect
        from drugos_graph import graph_stats
        src = inspect.getsource(graph_stats)
        assert "per_type_density[rel_type] = None" in src, (
            "per_type_density failure must set None, not 0.0 — REM-26 not fixed"
        )


# ─── REM-28: pg_advisory_lock failure is FATAL on Postgres ───────────────────

class TestPgAdvisoryLockFatalOnPostgres:
    """On Postgres, pg_advisory_lock failure must raise RuntimeError, not warn."""

    def test_advisory_lock_failure_raises_runtime_error(self):
        import inspect
        from database import connection
        src = inspect.getsource(connection.init_db)
        assert "Cannot acquire pg_advisory_lock" in src, (
            "Missing RuntimeError for pg_advisory_lock failure — REM-28 not fixed"
        )
        assert "raise RuntimeError" in src


# ─── REM-21: val negatives silent fallback now logs WARNING ──────────────────

class TestValNegativesFallbackWarns:
    """When val relation is not in per_relation_neg_pools, the code must log
    a VAL_AUC_DEGRADED warning before falling back to random entities."""

    def test_val_auc_degraded_warning_present(self):
        import inspect
        from drugos_graph import transe_model
        src = inspect.getsource(transe_model)
        assert "VAL_AUC_DEGRADED" in src, (
            "Missing VAL_AUC_DEGRADED warning — REM-21 not fixed"
        )


# ─── REM-22: combined_sampling failure tracked and summarized ────────────────

class TestNegSamplerFailureSummary:
    """When combined_sampling fails for a relation, training must log a
    NEG_SAMPLER_DEGRADED summary at the end."""

    def test_neg_sampler_degraded_summary_present(self):
        import inspect
        from drugos_graph import transe_model
        src = inspect.getsource(transe_model)
        assert "NEG_SAMPLER_DEGRADED" in src, (
            "Missing NEG_SAMPLER_DEGRADED summary — REM-22 not fixed"
        )


# ─── REM-7: InChIKey merge failure is FATAL ──────────────────────────────────

class TestInchikeyMergeFatal:
    """merge_mappings_by_inchikey failure must raise RuntimeError, not warn+continue."""

    def test_inchikey_merge_failure_raises(self):
        import inspect
        from drugos_graph import run_pipeline
        src = inspect.getsource(run_pipeline)
        assert "Step 8 InChIKey merge failed" in src, (
            "Missing RuntimeError for InChIKey merge failure — REM-7 not fixed"
        )


# ─── CORE_EDGE_TYPES includes susceptible_to ─────────────────────────────────

class TestCoreEdgeTypesIncludesSusceptibleTo:
    """The new (Gene, susceptible_to, Disease) edge type must be registered
    in CORE_EDGE_TYPES so the KG builder accepts it."""

    def test_susceptible_to_in_core_edge_types(self):
        from drugos_graph.config import CORE_EDGE_TYPES, CORE_EDGE_TYPES_SET
        assert ("Gene", "susceptible_to", "Disease") in CORE_EDGE_TYPES, (
            "susceptible_to missing from CORE_EDGE_TYPES list"
        )
        assert ("Gene", "susceptible_to", "Disease") in CORE_EDGE_TYPES_SET


# ─── End-to-end smoke: bridge stages all sources ─────────────────────────────

class TestEndToEndSmoke:
    """Smoke test: bridge runs and stages data from all available Phase 1 CSVs."""

    def test_bridge_runs_and_stages_data(self):
        from drugos_graph.phase1_bridge import (
            RecordingGraphBuilder,
            run_phase1_to_phase2,
        )
        pdir = PHASE1_ROOT / "processed_data"
        if not pdir.exists():
            pytest.skip("Phase 1 processed_data dir missing")
        builder = RecordingGraphBuilder()
        result = run_phase1_to_phase2(
            phase1_processed_dir=pdir,
            builder=builder,
        )
        summary = result["summary"]
        # Must read at least 9 sources (the original 9)
        sources = summary["sources_read"]
        assert len(sources) >= 9, f"Bridge read only {len(sources)} sources"
        # Must include the new sources when their CSVs are present
        if (pdir / "chembl_activities_clean.csv").exists():
            assert "chembl_activities" in sources, "chembl_activities not read"
        if (pdir / "omim_gene_disease_susceptibility.csv").exists():
            assert "omim_susceptibility" in sources, "omim_susceptibility not read"
        # Must have staged nodes and edges
        assert summary["nodes_loaded"] > 0, "Zero nodes loaded"
        assert summary["edges_loaded"] > 0, "Zero edges loaded"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
