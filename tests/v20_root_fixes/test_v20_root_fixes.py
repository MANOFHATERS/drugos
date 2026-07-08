"""V20 ROOT-FIX regression tests.

These tests verify the residual issues identified by the v11 forensic
audit that v19 had ONLY PARTIALLY FIXED. v20 closes them at root level.

Test categories:
- CD-2: protonation_state String(1) -> String(20) in ORM + Core Table
- CD-3 minor: GeneDiseaseAssociation CHECK constraints in ORM
- SF-5: OMIM HGNC validation strict-mode raise
- SF-7: GEO/ClinicalTrials critical_failure -> launch-blocking + sys.exit(1)
- SF-8: per-type density exception swallowing (mirror SF-9 pattern)
- SW-1 minor: is_fda_approved default False -> None
- SW-13: default uniprot_organism_crosswalk.yaml auto-loaded
- Compound-2/8 escape-hatch production guard
- Phase1<->Phase2 connection gap: name_map + run_unified --full-pipeline default

All tests run instantly (no module imports of heavy deps) where possible.
The runtime tests use mocked env vars to avoid breaking other tests.
"""

from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ===========================================================================
# CD-2: protonation_state type alignment
# ===========================================================================

class TestCD2ProtonationStateString20(unittest.TestCase):
    """CD-2 v20 ROOT FIX: protonation_state must be String(20) (VARCHAR(20))
    in ORM, Core Table, AND migration 005 — three-way alignment."""

    def test_orm_uses_string_20(self):
        models = (_PROJECT_ROOT / "phase1" / "database" / "models.py").read_text()
        # The ORM site for protonation_state must use String(20).
        # Find the protonation_state column definition.
        match = re.search(
            r"protonation_state[^S]*String\((\d+)\)",
            models,
        )
        self.assertIsNotNone(
            match,
            "ORM protonation_state column definition not found",
        )
        self.assertEqual(
            match.group(1), "20",
            f"ORM protonation_state must be String(20), got String({match.group(1)})",
        )

    def test_core_table_uses_string_20(self):
        loaders = (_PROJECT_ROOT / "phase1" / "database" / "loaders.py").read_text()
        # Find the Column("protonation_state", String(N)) line.
        match = re.search(
            r'Column\(\s*"protonation_state",\s*String\((\d+)\)',
            loaders,
        )
        self.assertIsNotNone(
            match,
            "Core Table protonation_state column definition not found",
        )
        self.assertEqual(
            match.group(1), "20",
            f"Core Table protonation_state must be String(20), got String({match.group(1)})",
        )

    def test_migration_005_uses_varchar_20(self):
        mig = (
            _PROJECT_ROOT / "phase1" / "database" / "migrations"
            / "005_pubchem_compound_properties.sql"
        ).read_text()
        # Migration 005 must declare protonation_state as VARCHAR(20).
        self.assertRegex(
            mig,
            r"protonation_state\s+VARCHAR\(20\)",
            "Migration 005 protonation_state must be VARCHAR(20)",
        )


# ===========================================================================
# CD-3 minor: ORM CHECK constraints
# ===========================================================================

class TestCD3GdaCheckConstraintsInOrm(unittest.TestCase):
    """CD-3 v20 ROOT FIX: ORM GeneDiseaseAssociation must declare the same
    CHECK (gene_symbol <> '') and CHECK (disease_id <> '') constraints
    that migration 001 lines 864-868 declare — SQLite-vs-PostgreSQL parity."""

    def test_orm_has_gene_symbol_nonempty_constraint(self):
        models = (_PROJECT_ROOT / "phase1" / "database" / "models.py").read_text()
        self.assertIn(
            "chk_gda_gene_symbol_nonempty",
            models,
            "ORM GeneDiseaseAssociation must declare "
            "chk_gda_gene_symbol_nonempty CHECK constraint",
        )

    def test_orm_has_disease_id_nonempty_constraint(self):
        models = (_PROJECT_ROOT / "phase1" / "database" / "models.py").read_text()
        self.assertIn(
            "chk_gda_disease_id_nonempty",
            models,
            "ORM GeneDiseaseAssociation must declare "
            "chk_gda_disease_id_nonempty CHECK constraint",
        )

    def test_constraints_compile_at_runtime(self):
        """Verify the constraints are real CheckConstraint objects on
        __table_args__, not just strings in comments."""
        sys.path.insert(0, str(_PROJECT_ROOT / "phase1"))
        try:
            from database.models import GeneDiseaseAssociation
            from sqlalchemy import CheckConstraint
            args = GeneDiseaseAssociation.__table_args__
            # __table_args__ may be a tuple of items.
            constraint_names = set()
            for item in args:
                if isinstance(item, CheckConstraint) and item.name:
                    constraint_names.add(item.name)
            self.assertIn(
                "chk_gda_gene_symbol_nonempty", constraint_names,
                "chk_gda_gene_symbol_nonempty not in actual table_args",
            )
            self.assertIn(
                "chk_gda_disease_id_nonempty", constraint_names,
                "chk_gda_disease_id_nonempty not in actual table_args",
            )
        finally:
            sys.path.pop(0)


# ===========================================================================
# SF-5: OMIM HGNC strict-mode raise
# ===========================================================================

class TestSF5OmimHgncStrictMode(unittest.TestCase):
    """SF-5 v20 ROOT FIX: OMIM pipeline must RAISE in strict mode when
    _load_hgnc_symbols() returns empty — not just log a warning."""

    def test_strict_mode_env_vars_consulted(self):
        omim = (
            _PROJECT_ROOT / "phase1" / "pipelines" / "omim_pipeline.py"
        ).read_text()
        # Must consult DRUGOS_STRICT and DRUGOS_OMIM_STRICT_HGNC.
        self.assertIn("DRUGOS_STRICT", omim)
        self.assertIn("DRUGOS_OMIM_STRICT_HGNC", omim)

    def test_strict_mode_raises_runtime_error(self):
        omim = (
            _PROJECT_ROOT / "phase1" / "pipelines" / "omim_pipeline.py"
        ).read_text()
        # The raise RuntimeError must be inside the strict-mode branch.
        self.assertIsNotNone(
            re.search(
                r"DRUGOS_OMIM_STRICT_HGNC.*?raise RuntimeError",
                omim, re.DOTALL,
            ),
            "OMIM pipeline must raise RuntimeError in strict mode when "
            "HGNC validation is skipped.",
        )


# ===========================================================================
# SF-7: GEO/ClinicalTrials critical_failure + launch criteria + sys.exit
# ===========================================================================

class TestSF7CriticalFailureLaunchBlocking(unittest.TestCase):
    """SF-7 v20 ROOT FIX: critical source-loader failures must be
    launch-blocking."""

    def test_chembl_critical_failure_consulted_by_launch_criteria(self):
        rp = (
            _PROJECT_ROOT / "phase2" / "drugos_graph" / "run_pipeline.py"
        ).read_text()
        self.assertIn("no_critical_source_failure", rp)
        self.assertIn("critical_failure_sources", rp)
        # Must be in the `passed = (...)` boolean expression.
        self.assertIn(
            "and criteria[\"no_critical_source_failure\"]",
            rp,
            "no_critical_source_failure must be in the launch-criteria "
            "`passed` boolean expression",
        )

    def test_geo_critical_failure_flag_in_strict_mode(self):
        rp = (
            _PROJECT_ROOT / "phase2" / "drugos_graph" / "run_pipeline.py"
        ).read_text()
        # GEO must set geo_critical_failure in strict mode.
        self.assertIn("DRUGOS_STRICT_GEO", rp)
        self.assertIn("geo_critical_failure", rp)

    def test_clinicaltrials_critical_failure_flag_in_strict_mode(self):
        rp = (
            _PROJECT_ROOT / "phase2" / "drugos_graph" / "run_pipeline.py"
        ).read_text()
        # ClinicalTrials must set clinicaltrials_critical_failure in strict mode.
        self.assertIn("DRUGOS_STRICT_CLINICALTRIALS", rp)
        self.assertIn("clinicaltrials_critical_failure", rp)

    def test_launch_criteria_failure_exits_1(self):
        rp = (
            _PROJECT_ROOT / "phase2" / "drugos_graph" / "run_pipeline.py"
        ).read_text()
        # When launch criteria fail (and DRUGOS_ALLOW_LAUNCH_FAIL != "1"),
        # the pipeline must sys.exit(1) — not just log a WARNING.
        self.assertIsNotNone(
            re.search(
                r"DRUGOS_ALLOW_LAUNCH_FAIL.*?sys\.exit\(1\)",
                rp, re.DOTALL,
            ),
            "Pipeline must sys.exit(1) when V1 launch criteria fail "
            "(unless DRUGOS_ALLOW_LAUNCH_FAIL=1).",
        )


# ===========================================================================
# SF-8: per-type density exception swallowing
# ===========================================================================

class TestSF8PerTypeDensityExceptionMirroring(unittest.TestCase):
    """SF-8 v20 ROOT FIX: per-type density must distinguish "query crashed"
    from "no edges" — mirroring the SF-9 pattern at lines 1110-1123."""

    def test_density_check_explicitly_tests_recs_is_none(self):
        gs = (
            _PROJECT_ROOT / "phase2" / "drugos_graph" / "graph_stats.py"
        ).read_text()
        # The per-type density loop must explicitly check
        # `if recs is None:` BEFORE the `if recs and recs[0] is not None:`
        # branch — because _run_query swallows exceptions and returns None.
        self.assertIsNotNone(
            re.search(
                r"per_type_density\[rel_type\] = None\s*\n\s*warnings\.append",
                gs, re.DOTALL,
            ),
            "Per-type density must set None (not 0.0) and append a warning "
            "when _run_query returns None.",
        )

    def test_density_check_does_not_silently_set_zero_on_failure(self):
        gs = (
            _PROJECT_ROOT / "phase2" / "drugos_graph" / "graph_stats.py"
        ).read_text()
        # The pattern `else: per_type_density[rel_type] = 0.0` is OK ONLY
        # if it's the legitimate-empty-result branch. The v19 bug had it
        # fire on _run_query returning None. Verify the new code has the
        # explicit `if recs is None:` short-circuit BEFORE the
        # `if recs and recs[0] is not None:` check.
        idx_none_check = gs.find("if recs is None:")
        idx_truthy_check = gs.find("if recs and recs[0] is not None:")
        self.assertGreater(
            idx_none_check, -1,
            "graph_stats.py: `if recs is None:` check not found in "
            "per-type density loop",
        )
        self.assertGreater(
            idx_truthy_check, -1,
            "graph_stats.py: `if recs and recs[0] is not None:` check "
            "not found in per-type density loop",
        )
        self.assertLess(
            idx_none_check, idx_truthy_check,
            "graph_stats.py: `if recs is None:` check must come BEFORE "
            "the truthy check in the per-type density loop",
        )


# ===========================================================================
# SW-1 minor: is_fda_approved default
# ===========================================================================

class TestSW1IsFdaApprovedDefaultNone(unittest.TestCase):
    """SW-1 v20 minor ROOT FIX: _ensure_drug_columns default for
    is_fda_approved must be None (not False)."""

    def test_default_is_none_not_false(self):
        chembl = (
            _PROJECT_ROOT / "phase1" / "pipelines" / "chembl_pipeline.py"
        ).read_text()
        # Find the defaults dict.
        m = re.search(
            r'defaults:\s*dict\[str,\s*Any\]\s*=\s*\{[^}]*"is_fda_approved":\s*(\w+)',
            chembl, re.DOTALL,
        )
        self.assertIsNotNone(m, "defaults dict not found in chembl_pipeline.py")
        self.assertEqual(
            m.group(1), "None",
            f"is_fda_approved default must be None, got {m.group(1)}",
        )


# ===========================================================================
# SW-13: default organism crosswalk file
# ===========================================================================

class TestSW13DefaultOrganismCrosswalk(unittest.TestCase):
    """SW-13 v20 ROOT FIX: ship a default uniprot_organism_crosswalk.yaml
    and auto-load it at module import time."""

    def test_default_yaml_file_exists(self):
        p = (
            _PROJECT_ROOT / "phase1" / "data"
            / "uniprot_organism_crosswalk.yaml"
        )
        self.assertTrue(
            p.exists(),
            f"Default organism crosswalk file must exist at {p}",
        )

    def test_yaml_contains_known_accessions(self):
        p = (
            _PROJECT_ROOT / "phase1" / "data"
            / "uniprot_organism_crosswalk.yaml"
        )
        content = p.read_text()
        # Must contain TP53 (P04637) -> Homo sapiens.
        self.assertIn("P04637", content)
        self.assertIn("Homo sapiens", content)
        # Must contain at least one non-human entry (mouse/rat/yeast).
        self.assertIn("Mus musculus", content)

    def test_protein_resolver_auto_loads_default(self):
        # The protein_resolver module must have the auto-load logic.
        pr = (
            _PROJECT_ROOT / "phase1" / "entity_resolution"
            / "protein_resolver.py"
        ).read_text()
        self.assertIn(
            "uniprot_organism_crosswalk.yaml",
            pr,
            "protein_resolver.py must reference the default crosswalk file",
        )
        self.assertIn(
            "_DEFAULT_CROSSWALK_PATH",
            pr,
            "protein_resolver.py must define _DEFAULT_CROSSWALK_PATH",
        )

    def test_protein_resolver_loads_default_at_runtime(self):
        """End-to-end: import the module and verify the default file
        is loaded into _RUNTIME_OVERRIDES (unless overridden by env var)."""
        # Clear env var to test the default-load path.
        old = os.environ.pop("UNIPROT_ORGANISM_CROSSWALK_PATH", None)
        try:
            sys.path.insert(0, str(_PROJECT_ROOT / "phase1"))
            # Force a fresh import.
            mods_to_del = [
                k for k in sys.modules
                if k.startswith("entity_resolution.protein_resolver")
            ]
            for k in mods_to_del:
                del sys.modules[k]
            try:
                from entity_resolution.protein_resolver import (
                    _get_effective_uniprot_organism_overrides,
                )
                overrides = _get_effective_uniprot_organism_overrides()
                # Must have substantially more than the ~50 hardcoded entries.
                self.assertGreater(
                    len(overrides), 100,
                    f"Default crosswalk not auto-loaded: only {len(overrides)} "
                    f"entries (expected >100 from default YAML)",
                )
                # Spot-check a few accessions that are ONLY in the default
                # YAML (not in the hardcoded dict).
                self.assertEqual(overrides.get("P04637"), "Homo sapiens")
                self.assertEqual(overrides.get("P08684"), "Homo sapiens")  # CYP3A4
                self.assertEqual(overrides.get("P02340"), "Mus musculus")
            finally:
                sys.path.pop(0)
        finally:
            if old is not None:
                os.environ["UNIPROT_ORGANISM_CROSSWALK_PATH"] = old


# ===========================================================================
# Compound-2/8: production escape-hatch guard
# ===========================================================================

class TestCompound28ProductionEscapeHatchGuard(unittest.TestCase):
    """Compound-2/8 v20 ROOT FIX: the module-import guard must refuse
    to load if any escape-hatch flag is set when DRUGOS_ENVIRONMENT=production."""

    def test_guard_function_exists(self):
        rp = (
            _PROJECT_ROOT / "phase2" / "drugos_graph" / "run_pipeline.py"
        ).read_text()
        self.assertIn("_check_production_escape_hatches", rp)

    def test_guard_fires_for_no_sampler_in_production(self):
        old_env = os.environ.get("DRUGOS_ENVIRONMENT", "")
        old_flag = os.environ.get("DRUGOS_ALLOW_NO_SAMPLER", "")
        os.environ["DRUGOS_ENVIRONMENT"] = "production"
        os.environ["DRUGOS_ALLOW_NO_SAMPLER"] = "1"
        try:
            sys.path.insert(0, str(_PROJECT_ROOT))
            # Re-import run_pipeline (will re-execute module-level guard).
            mods_to_del = [
                k for k in sys.modules
                if k.startswith("phase2.drugos_graph.run_pipeline")
            ]
            for k in mods_to_del:
                del sys.modules[k]
            with self.assertRaises(RuntimeError) as ctx:
                import phase2.drugos_graph.run_pipeline  # noqa: F401
            self.assertIn("REFUSING TO LOAD", str(ctx.exception))
            self.assertIn("DRUGOS_ALLOW_NO_SAMPLER", str(ctx.exception))
        finally:
            if old_env:
                os.environ["DRUGOS_ENVIRONMENT"] = old_env
            else:
                os.environ.pop("DRUGOS_ENVIRONMENT", None)
            if old_flag:
                os.environ["DRUGOS_ALLOW_NO_SAMPLER"] = old_flag
            else:
                os.environ.pop("DRUGOS_ALLOW_NO_SAMPLER", None)
            # Force re-import with safe env.
            for k in list(sys.modules):
                if k.startswith("phase2.drugos_graph.run_pipeline"):
                    del sys.modules[k]
            sys.path.pop(0)

    def test_guard_does_not_fire_in_dev(self):
        """In dev environment, escape hatches must remain available."""
        old_env = os.environ.get("DRUGOS_ENVIRONMENT", "")
        os.environ["DRUGOS_ENVIRONMENT"] = "dev"
        try:
            sys.path.insert(0, str(_PROJECT_ROOT))
            # Re-import run_pipeline.
            for k in list(sys.modules):
                if k.startswith("phase2.drugos_graph.run_pipeline"):
                    del sys.modules[k]
            try:
                import phase2.drugos_graph.run_pipeline  # noqa: F401
                # If we get here, the guard did not fire — correct.
            finally:
                sys.path.pop(0)
        finally:
            if old_env:
                os.environ["DRUGOS_ENVIRONMENT"] = old_env
            else:
                os.environ.pop("DRUGOS_ENVIRONMENT", None)


# ===========================================================================
# Compound-8: legacy single-pool fallback promotion
# ===========================================================================

class TestCompound8LegacyFallbackRaisesByDefault(unittest.TestCase):
    """Compound-8 v20 ROOT FIX: the legacy single-pool negative sampling
    fallback in transe_model.py must RAISE RuntimeError by default —
    not just log WARNING."""

    def test_legacy_fallback_raises_without_escape_hatch(self):
        tm = (
            _PROJECT_ROOT / "phase2" / "drugos_graph" / "transe_model.py"
        ).read_text()
        # The legacy fallback block must contain a raise RuntimeError
        # guarded by the DRUGOS_ALLOW_NO_SAMPLER escape hatch.
        self.assertIsNotNone(
            re.search(
                r"DRUGOS_ALLOW_NO_SAMPLER.*?raise RuntimeError",
                tm, re.DOTALL,
            ),
            "Legacy single-pool negative sampling fallback must raise "
            "RuntimeError when DRUGOS_ALLOW_NO_SAMPLER is not set.",
        )


# ===========================================================================
# Phase1 <-> Phase2 connection gap fixes
# ===========================================================================

class TestPhaseConnectionNameMapComplete(unittest.TestCase):
    """Phase1<->Phase2 v20 ROOT FIX: step1_load_phase1 name_map must
    include chembl_activities and omim_susceptibility."""

    def test_name_map_includes_chembl_activities(self):
        rp = (
            _PROJECT_ROOT / "phase2" / "drugos_graph" / "run_pipeline.py"
        ).read_text()
        self.assertIn(
            '"chembl_activities":',
            rp,
            "step1 name_map must include chembl_activities for full lineage",
        )
        self.assertIn(
            "chembl_activities_clean.csv",
            rp,
            "chembl_activities entry must reference chembl_activities_clean.csv",
        )

    def test_name_map_includes_omim_susceptibility(self):
        rp = (
            _PROJECT_ROOT / "phase2" / "drugos_graph" / "run_pipeline.py"
        ).read_text()
        self.assertIn(
            '"omim_susceptibility":',
            rp,
            "step1 name_map must include omim_susceptibility for full lineage",
        )
        self.assertIn(
            "omim_gene_disease_susceptibility.csv",
            rp,
            "omim_susceptibility entry must reference the actual filename",
        )


class TestRunUnifiedFullPipelineDefault(unittest.TestCase):
    """Phase1<->Phase2 v20 ROOT FIX: run_unified.py --full-pipeline must
    default to True so the bridge actually chains into TransE training."""

    def test_full_pipeline_default_true(self):
        ru = (_PROJECT_ROOT / "run_unified.py").read_text()
        # Must have default=True on --full-pipeline.
        m = re.search(
            r'"--full-pipeline",\s*action="store_true",\s*default=(\w+)',
            ru,
        )
        self.assertIsNotNone(m, "--full-pipeline default not found")
        self.assertEqual(
            m.group(1), "True",
            f"--full-pipeline default must be True, got {m.group(1)}",
        )

    def test_no_full_pipeline_opt_out_exists(self):
        ru = (_PROJECT_ROOT / "run_unified.py").read_text()
        self.assertIn(
            "--no-full-pipeline",
            ru,
            "--no-full-pipeline opt-out flag must exist for dev/test",
        )


if __name__ == "__main__":
    unittest.main()
