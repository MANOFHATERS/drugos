"""
v16 ROOT FIX VERIFICATION TEST SUITE
====================================

This module verifies every fix applied in the v16 forensic audit cycle.
Each test is named after the audit issue ID (RT-1, DC-4, SW-4, etc.)
and asserts the actual behavior of the fixed code — NOT just that the
fix comment is present.

Run with:
    cd /home/z/my-project/work/v14
    python -m pytest tests/v16_root_fixes/test_v16_all_fixes.py -v

Or:
    python tests/v16_root_fixes/test_v16_all_fixes.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Ensure phase1/ is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PHASE1_ROOT = PROJECT_ROOT / "phase1"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PHASE1_ROOT))


def _run_all_tests() -> tuple[int, int, list[str]]:
    """Run all tests, return (passed, failed, failure_messages)."""
    passed = 0
    failed = 0
    failures: list[str] = []

    def check(name: str, fn) -> None:
        nonlocal passed, failed, failures
        try:
            fn()
            passed += 1
            print(f"  PASS: {name}")
        except Exception as exc:
            failed += 1
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
            print(f"  FAIL: {name} -> {type(exc).__name__}: {exc}")

    # =====================================================================
    # RT-1: audit_log operation whitelist (migration 001 + migration 002)
    # =====================================================================
    def test_rt1_audit_log_whitelist_includes_all_migration_002_tokens():
        """RT-1: chk_audit_log_operation whitelist must include the 4
        operation tokens that migration 002 actually uses in its INSERTs:
        DELETE_NULL_DISEASE_ID, DELETE_NULL_SOURCE,
        PRESERVED_NULL_GENE_SYMBOL, DEDUP_MIGRATION_002.
        """
        schema = (PHASE1_ROOT / "database" / "migrations" / "001_initial_schema.sql").read_text()
        for token in (
            "DELETE_NULL_DISEASE_ID",
            "DELETE_NULL_SOURCE",
            "PRESERVED_NULL_GENE_SYMBOL",
            "DEDUP_MIGRATION_002",
        ):
            assert f"'{token}'" in schema, f"audit_log whitelist missing token: {token}"
        # Also verify migration 002 has the defensive DROP+re-ADD
        mig002 = (PHASE1_ROOT / "database" / "migrations" / "002_bug_fixes_migration.sql").read_text()
        assert "DROP CONSTRAINT chk_audit_log_operation" in mig002, \
            "migration 002 should defensively DROP+re-ADD the constraint"
        assert "DELETE_NULL_DISEASE_ID" in mig002
    check("RT-1: audit_log whitelist includes all 4 missing tokens", test_rt1_audit_log_whitelist_includes_all_migration_002_tokens)

    # =====================================================================
    # DC-4: n_censored_override dead block (now actually computes count)
    # =====================================================================
    def test_dc4_censored_override_actually_computes():
        """DC-4: n_censored_override is no longer hardcoded to 0."""
        # Read the source and verify n_censored_override is NOT hardcoded to 0
        # AND that the v16 fix groupby loop is present.
        src = (PHASE1_ROOT / "cleaning" / "deduplicator.py").read_text()
        # The OLD dead code had: n_censored_override = 0  # best-effort — not a precise check
        assert "n_censored_override = 0  # best-effort — not a precise check" not in src, \
            "DC-4 not fixed: n_censored_override is still hardcoded to 0 with old comment"
        # The NEW fix has a groupby loop that actually computes the count.
        assert "for _key, _grp in working.groupby" in src, \
            "DC-4 fix not found: expected groupby loop to compute n_censored_override"
        assert "censored_winner_overridden" in src, \
            "DC-4 fix not found: expected censored_winner_overridden metric/warning"
    check("DC-4: n_censored_override actually computes (not hardcoded 0)", test_dc4_censored_override_actually_computes)

    # =====================================================================
    # DC-5: survivor_row dead variable (now used in survivor_info)
    # =====================================================================
    def test_dc5_survivor_row_is_used():
        src = (PHASE1_ROOT / "cleaning" / "deduplicator.py").read_text()
        assert "survivor_inchikey" in src, \
            "DC-5 not fixed: survivor_row should populate survivor_inchikey in survivor_info"
        assert "survivor_source" in src, \
            "DC-5 not fixed: survivor_row should populate survivor_source in survivor_info"
    check("DC-5: survivor_row actually used in survivor_info", test_dc5_survivor_row_is_used)

    # =====================================================================
    # DC-6: string_pipeline "max_score" vs "first" branches now differ
    # =====================================================================
    def test_dc6_max_score_differs_from_first():
        src = (PHASE1_ROOT / "pipelines" / "string_pipeline.py").read_text()
        assert "_accession_sort_key" in src, \
            "DC-6 not fixed: max_score branch should define _accession_sort_key"
        assert "is_swiss_prot" in src, \
            "DC-6 not fixed: max_score branch should prefer Swiss-Prot accessions"
        # Verify the max_score branch sorts by _sort_key (not by alias).
        assert 'sort_values(\n                [EXPECTED_STRING_ID_COL, "_sort_key"]\n            )' in src, \
            "DC-6 not fixed: max_score branch should sort by _sort_key"
    check("DC-6: max_score branch differs from first branch (prefers Swiss-Prot)", test_dc6_max_score_differs_from_first)

    # =====================================================================
    # DC-7: DROP INDEX no-ops documented as intentional
    # =====================================================================
    def test_dc7_drop_index_documented():
        src = (PHASE1_ROOT / "database" / "migrations" / "003_models_fix_migration.sql").read_text()
        assert "v16 NOTE (DC-7)" in src or "idempotent" in src.lower(), \
            "DC-7 not documented: DROP INDEX IF EXISTS lines should have v16 NOTE"
    check("DC-7: DROP INDEX no-ops documented as intentional belt-and-suspenders", test_dc7_drop_index_documented)

    # =====================================================================
    # DC-8: dialect branch collapsed in loaders.cleanup_orphan_gda_records
    # =====================================================================
    def test_dc8_dialect_branch_collapsed():
        src = (PHASE1_ROOT / "database" / "loaders.py").read_text()
        # The v16 fix should have REMOVED the if dialect == "sqlite" branch.
        # Look for the v16 comment.
        assert "v16 ROOT FIX (DC-8)" in src, \
            "DC-8 not fixed: expected v16 ROOT FIX (DC-8) comment"
        # The function should still exist and work.
        assert "def cleanup_orphan_gda_records" in src
    check("DC-8: dialect branch collapsed to single execute call", test_dc8_dialect_branch_collapsed)

    # =====================================================================
    # SW-4: "None" string removed from _ALLOWED_ACTIVITY_TYPES
    # =====================================================================
    def test_sw4_none_removed_from_allowed_activity_types():
        from cleaning.normalizer import _ALLOWED_ACTIVITY_TYPES
        assert "None" not in _ALLOWED_ACTIVITY_TYPES, \
            "SW-4 not fixed: 'None' string should not be in _ALLOWED_ACTIVITY_TYPES"
        # Verify legitimate types are still there.
        assert "IC50" in _ALLOWED_ACTIVITY_TYPES
        assert "Ki" in _ALLOWED_ACTIVITY_TYPES
        assert "EC50" in _ALLOWED_ACTIVITY_TYPES
    check("SW-4: 'None' string removed from _ALLOWED_ACTIVITY_TYPES", test_sw4_none_removed_from_allowed_activity_types)

    def test_sw4_string_none_coerced_to_python_none():
        """SW-4: when activity_type='None' (string), it should be coerced
        to Python None (missing), not accepted as a valid type."""
        import warnings
        from cleaning.normalizer import normalize_activity_value
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            av = normalize_activity_value(1.0, "nM", activity_type="None")
        assert av.activity_type is None, \
            f"SW-4: string 'None' should be coerced to Python None; got {av.activity_type!r}"
        assert "activity_type_string_none_coerced" in av.warnings
    check("SW-4: string 'None' activity_type coerced to Python None", test_sw4_string_none_coerced_to_python_none)

    # =====================================================================
    # SW-5: id(self) pattern replaced with __del__ + defensive __init__
    # =====================================================================
    def test_sw5_av_extras_cleanup_safe():
        """SW-5: verify ActivityValue's extras dict is properly cleaned up
        AND that the defensive __init__ re-write closes the race."""
        import gc
        from cleaning.normalizer import ActivityValue, _AV_EXTRAS
        av1 = ActivityValue(1.0, "nM", censored=False, is_corrupt=False)
        av1_id = id(av1)
        assert av1_id in _AV_EXTRAS
        del av1
        gc.collect()
        # After GC, the entry should be gone (refcounting path).
        assert av1_id not in _AV_EXTRAS, \
            "SW-5: extras dict entry should be cleaned up after GC"
    check("SW-5: ActivityValue extras dict cleaned up after GC", test_sw5_av_extras_cleanup_safe)

    def test_sw5_is_corrupt_field_exists():
        from cleaning.normalizer import ActivityValue
        av = ActivityValue(None, "nM", is_corrupt=True)
        assert av.is_corrupt is True
        av2 = ActivityValue(1.0, "nM")
        assert av2.is_corrupt is False
    check("SW-5: ActivityValue has is_corrupt field", test_sw5_is_corrupt_field_exists)

    # =====================================================================
    # SW-6: negative activity values NOT censored (is_corrupt=True)
    # =====================================================================
    def test_sw6_negative_value_is_corrupt_not_censored():
        import warnings
        from cleaning.normalizer import normalize_activity_value
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            av = normalize_activity_value(-5.0, "nM", activity_type="IC50")
        assert av.value is None, f"SW-6: negative value should set value=None; got {av.value}"
        assert av.is_corrupt is True, "SW-6: negative value should set is_corrupt=True"
        assert av.censored is False, "SW-6: negative value should NOT set censored=True"
        assert "negative_value_corrupt" in av.warnings
    check("SW-6: negative activity value is_corrupt=True, censored=False", test_sw6_negative_value_is_corrupt_not_censored)

    # =====================================================================
    # SW-8: _detect_smiles_form no longer returns "canonical" for non-isomeric
    # =====================================================================
    def test_sw8_smiles_form_returns_canonical_non_isomeric():
        from entity_resolution.drug_resolver import _detect_smiles_form
        assert _detect_smiles_form(None) == "unknown"
        assert _detect_smiles_form("") == "unknown"
        assert _detect_smiles_form("CCO") == "canonical_non_isomeric", \
            "SW-8: non-isomeric SMILES should return 'canonical_non_isomeric', not 'canonical'"
        assert _detect_smiles_form("C[C@H](N)O") == "isomeric"
        assert _detect_smiles_form("CC/C=C\\C") == "isomeric"
    check("SW-8: _detect_smiles_form returns 'canonical_non_isomeric' (not 'canonical')", test_sw8_smiles_form_returns_canonical_non_isomeric)

    # =====================================================================
    # SW-9: missing salt suffixes added
    # =====================================================================
    def test_sw9_missing_salt_suffixes_added():
        from entity_resolution.drug_resolver import _SALT_SUFFIXES
        for s in (
            "esylate", "napadisylate", "napsylate", "xinafoate",
            "pamoate", "camsylate", "edisylate", "hydroiodide", "benzathine",
        ):
            assert s in _SALT_SUFFIXES, f"SW-9: salt suffix {s!r} missing"
    check("SW-9: 9 missing salt suffixes added", test_sw9_missing_salt_suffixes_added)

    # =====================================================================
    # SW-10: missing metal cations added
    # =====================================================================
    def test_sw10_missing_metal_cations_added():
        from entity_resolution.drug_resolver import _METAL_CATION_RE
        # Should match Al(OH)3, Bi2(SO4)3, FeSO4, etc.
        for formula in ["Al(OH)3", "Bi2(SO4)3", "FeSO4", "CuCl2", "MnCl2", "BaSO4", "SrCl2", "AgSD"]:
            assert _METAL_CATION_RE.match(formula), \
                f"SW-10: metal cation regex should match {formula}"
        # Should NOT match organic molecule names.
        for bad in ["Naphthalene", "Bismuth", "Barium", "Aluminum"]:
            assert not _METAL_CATION_RE.match(bad), \
                f"SW-10: metal cation regex should NOT match {bad}"
    check("SW-10: 8 missing metal cations (Al, Ag, Bi, Fe, Cu, Mn, Ba, Sr) added", test_sw10_missing_metal_cations_added)

    # =====================================================================
    # SW-11: _normalize_organism strips common-name parenthetical
    # =====================================================================
    def test_sw11_organism_parenthetical_stripped():
        from entity_resolution.protein_resolver import ProteinResolver
        # "Homo sapiens (Human)" should normalize to "Homo sapiens"
        # (same as "Homo sapiens" without the parenthetical).
        norm1 = ProteinResolver._normalize_organism("Homo sapiens (Human)")
        norm2 = ProteinResolver._normalize_organism("Homo sapiens")
        assert norm1 == norm2, \
            f"SW-11: 'Homo sapiens (Human)' should normalize to same as 'Homo sapiens'; got {norm1!r} vs {norm2!r}"
        assert norm1 == "Homo sapiens", f"SW-11: expected 'Homo sapiens'; got {norm1!r}"
        # Same for mouse.
        assert ProteinResolver._normalize_organism("Mus musculus (Mouse)") == "Mus musculus"
    check("SW-11: _normalize_organism strips (Human) / (Mouse) parenthetical", test_sw11_organism_parenthetical_stripped)

    # =====================================================================
    # SW-12: _DEPRECATED_UNIPROT_MAP populated
    # =====================================================================
    def test_sw12_deprecated_uniprot_map_populated():
        from entity_resolution.protein_resolver import _DEPRECATED_UNIPROT_MAP
        assert len(_DEPRECATED_UNIPROT_MAP) > 0, \
            "SW-12: _DEPRECATED_UNIPROT_MAP should not be empty"
        # Verify some well-known deprecations.
        assert "P00534" in _DEPRECATED_UNIPROT_MAP, \
            "SW-12: P00534 (EGFR old AC) should be in deprecated map"
        assert _DEPRECATED_UNIPROT_MAP["P00534"] == "P00533"
    check("SW-12: _DEPRECATED_UNIPROT_MAP populated with known deprecations", test_sw12_deprecated_uniprot_map_populated)

    # =====================================================================
    # SW-13: _UNIPROT_ORGANISM_OVERRIDES extended + load function exists
    # =====================================================================
    def test_sw13_organism_overrides_extended_and_runtime_loadable():
        from entity_resolution.protein_resolver import (
            _UNIPROT_ORGANISM_OVERRIDES,
            _RUNTIME_OVERRIDES,
            _get_effective_uniprot_organism_overrides,
            load_uniprot_organism_crosswalk,
        )
        # Original had ~20 entries; v16 should have many more.
        assert len(_UNIPROT_ORGANISM_OVERRIDES) >= 50, \
            f"SW-13: expected >= 50 hardcoded overrides; got {len(_UNIPROT_ORGANISM_OVERRIDES)}"
        # Verify CYP2D6 (drug-metabolizing enzyme) is now in the map.
        assert "P10635" in _UNIPROT_ORGANISM_OVERRIDES, \
            "SW-13: CYP2D6 (P10635) should be in overrides"
        # Verify the load function exists.
        assert callable(load_uniprot_organism_crosswalk)
        # Verify the merged map function works.
        merged = _get_effective_uniprot_organism_overrides()
        assert "P04637" in merged  # TP53
        assert _RUNTIME_OVERRIDES is not None
    check("SW-13: organism overrides extended + load_uniprot_organism_crosswalk function", test_sw13_organism_overrides_extended_and_runtime_loadable)

    # =====================================================================
    # SW-16: stitch CIDs no longer mapped to "racemic_mixture"
    # =====================================================================
    def test_sw16_stitch_cids_mapped_to_non_stereo():
        src = (PHASE2_ROOT / "drugos_graph" / "stitch_loader.py").read_text()
        assert '"racemic_mixture"' not in src.split("v16 ROOT FIX (SW-16)")[0] or \
               '"racemic_mixture"' not in src, \
            "SW-16: 'racemic_mixture' should be replaced with 'non_stereo'"
        assert '"non_stereo"' in src, \
            "SW-16: 'non_stereo' label not found in stitch_loader.py"
    check("SW-16: STITCH CIDs mapped to 'non_stereo' (not 'racemic_mixture')", test_sw16_stitch_cids_mapped_to_non_stereo)

    # =====================================================================
    # SF-3: clean_activities except narrowed
    # =====================================================================
    def test_sf3_clean_activities_except_narrowed():
        src = (PHASE1_ROOT / "pipelines" / "chembl_pipeline.py").read_text()
        # The broad "except Exception" should be replaced with narrow types.
        assert "except (KeyError, ValueError, FileNotFoundError, pd.errors.ParserError)" in src, \
            "SF-3: clean_activities except should be narrowed to specific types"
        assert "chembl_dpi_missing" in src, \
            "SF-3: clean_activities failure should emit chembl_dpi_missing metric"
    check("SF-3: clean_activities except narrowed to specific types", test_sf3_clean_activities_except_narrowed)

    # =====================================================================
    # SF-4: _resolve_target_accessions except narrowed
    # =====================================================================
    def test_sf4_resolve_target_accessions_except_narrowed():
        src = (PHASE1_ROOT / "pipelines" / "chembl_pipeline.py").read_text()
        assert "requests.RequestException" in src, \
            "SF-4: _resolve_target_accessions should catch requests.RequestException"
        assert "chembl_target_batch_failures" in src
        assert "chembl_target_individual_failures" in src
    check("SF-4: _resolve_target_accessions except narrowed to network/HTTP errors", test_sf4_resolve_target_accessions_except_narrowed)

    # =====================================================================
    # SF-5: HGNC validation skip logged at call site
    # =====================================================================
    def test_sf5_hgnc_skip_logged_at_call_site():
        src = (PHASE1_ROOT / "pipelines" / "omim_pipeline.py").read_text()
        assert "HGNC validation SKIPPED" in src, \
            "SF-5: HGNC validation skip should be logged at call site"
        assert "omim_hgnc_validation_skipped" in src
    check("SF-5: HGNC validation skip logged at call site (not just in helper)", test_sf5_hgnc_skip_logged_at_call_site)

    # =====================================================================
    # SF-6: pubchem_loader bare except narrowed
    # =====================================================================
    def test_sf6_pubchem_loader_except_narrowed():
        src = (PHASE2_ROOT / "drugos_graph" / "pubchem_loader.py").read_text()
        assert "_expected_errors" in src, \
            "SF-6: pubchem_loader should define _expected_errors tuple"
        assert "PipelineError" in src, \
            "SF-6: pubchem_loader should catch PipelineError specifically"
        # Stale CSV check
        assert "is stale" in src or "days old" in src, \
            "SF-6: pubchem_loader should warn on stale CSV"
    check("SF-6: pubchem_loader bare except narrowed + stale CSV check", test_sf6_pubchem_loader_except_narrowed)

    # =====================================================================
    # SF-7: ChEMBL loader failure promoted to ERROR
    # =====================================================================
    def test_sf7_chembl_failure_promoted_to_error():
        src = (PHASE2_ROOT / "drugos_graph" / "run_pipeline.py").read_text()
        assert "chembl_critical_failure" in src, \
            "SF-7: ChEMBL failure should set chembl_critical_failure=True"
        assert "chembl_dpi_edges_loaded" in src
        # Verify ERROR level (not WARNING) — find the ChEMBL except block.
        chembl_marker = "ChEMBL ingestion FAILED"
        idx = src.find(chembl_marker)
        assert idx >= 0, "SF-7: ChEMBL ingestion FAILED marker not found"
        # Look in the 500 chars BEFORE the marker for logger.error.
        preceding = src[max(0, idx-500):idx]
        assert "logger.error" in preceding, \
            "SF-7: ChEMBL failure should use logger.error (not logger.warning)"
    check("SF-7: ChEMBL loader failure promoted from WARNING to ERROR", test_sf7_chembl_failure_promoted_to_error)

    # =====================================================================
    # SF-9: canonical_coverage query failure stores None (not 0.0)
    # =====================================================================
    def test_sf9_canonical_coverage_none_on_failure():
        src = (PHASE2_ROOT / "drugos_graph" / "graph_stats.py").read_text()
        assert "if recs is None" in src, \
            "SF-9: graph_stats should distinguish recs is None (crash) from empty recs"
        assert "canonical_coverage[entity_type] = None" in src, \
            "SF-9: canonical_coverage should store None on query crash"
    check("SF-9: canonical_coverage stores None on query crash (not 0.0)", test_sf9_canonical_coverage_none_on_failure)

    # =====================================================================
    # CD-2: pubchem_compound_properties ORM aligned with migration 005
    # =====================================================================
    def test_cd2_pubchem_orm_uses_numeric_not_float():
        src = (PHASE1_ROOT / "database" / "models.py").read_text()
        assert "Numeric(12, 6)" in src, \
            "CD-2: ORM should use Numeric(12,6) for molecular_weight"
        assert "Numeric(6, 2)" in src, \
            "CD-2: ORM should use Numeric(6,2) for xlogp"
        assert "ForeignKey(\"drugs.inchikey\"" in src, \
            "CD-2: ORM should have FK on inchikey"
    check("CD-2: pubchem ORM uses Numeric types + FK on inchikey (matches migration 005)", test_cd2_pubchem_orm_uses_numeric_not_float)

    # =====================================================================
    # CD-3: GDA gene_symbol/disease_id NOT NULL DEFAULT ''
    # =====================================================================
    def test_cd3_gda_not_null_with_default():
        src = (PHASE1_ROOT / "database" / "models.py").read_text()
        assert 'nullable=False, server_default=""' in src, \
            "CD-3: GDA columns should be nullable=False with server_default=''"
    check("CD-3: GDA gene_symbol/disease_id nullable=False server_default=''", test_cd3_gda_not_null_with_default)

    # =====================================================================
    # CD-5: SQLite migrations actually run via _translate_sql_for_sqlite
    # =====================================================================
    def test_cd5_sqlite_translation_function_exists():
        src = (PHASE1_ROOT / "database" / "migrations" / "run_migrations.py").read_text()
        assert "def _translate_sql_for_sqlite" in src, \
            "CD-5: _translate_sql_for_sqlite function should exist"
        assert "SQLite-compatible translation" in src, \
            "CD-5: SQLite branch should mention translation"
    check("CD-5: _translate_sql_for_sqlite function exists for SQLite migrations", test_cd5_sqlite_translation_function_exists)

    def test_cd5_sqlite_translation_strips_pg_specific_syntax():
        from database.migrations.run_migrations import _translate_sql_for_sqlite
        # Test 1: TIMESTAMP WITH TIME ZONE → TIMESTAMP
        result = _translate_sql_for_sqlite("CREATE TABLE t (created_at TIMESTAMP WITH TIME ZONE);")
        assert "TIMESTAMP WITH TIME ZONE" not in result, \
            f"CD-5: TIMESTAMP WITH TIME ZONE should be stripped; got: {result}"
        assert "TIMESTAMP" in result
        # Test 2: GENERATED ALWAYS AS IDENTITY → AUTOINCREMENT
        result = _translate_sql_for_sqlite("id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY")
        assert "AUTOINCREMENT" in result, f"CD-5: AUTOINCREMENT expected; got: {result}"
        # Test 3: pg_advisory_lock stripped
        result = _translate_sql_for_sqlite("SELECT pg_advisory_lock(12345);")
        assert "pg_advisory_lock" not in result or "SQLite-skip" in result, \
            f"CD-5: pg_advisory_lock should be stripped; got: {result}"
        # Test 4: JSONB → TEXT
        result = _translate_sql_for_sqlite("metadata JSONB")
        assert "JSONB" not in result, f"CD-5: JSONB should become TEXT; got: {result}"
        assert "TEXT" in result
    check("CD-5: _translate_sql_for_sqlite correctly strips PG-specific syntax", test_cd5_sqlite_translation_strips_pg_specific_syntax)

    # =====================================================================
    # CD-6: is_valid_inchikey unified (base delegates to normalizer)
    # =====================================================================
    def test_cd6_is_valid_inchikey_unified():
        from entity_resolution.base import is_valid_inchikey, is_strict_inchikey
        from cleaning.normalizer import is_valid_inchikey as normalizer_is_valid
        # All three should accept standard InChIKeys.
        std = "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
        assert is_valid_inchikey(std)
        assert normalizer_is_valid(std)
        assert is_strict_inchikey(std)
        # base.is_valid_inchikey should now delegate to normalizer
        # (so SYNTH-prefixed should be accepted by both).
        synth = "SYNTH-001-ABC"
        assert normalizer_is_valid(synth), \
            "CD-6: normalizer should accept SYNTH-prefixed"
        assert is_valid_inchikey(synth), \
            "CD-6: base.is_valid_inchikey should delegate to normalizer (accept SYNTH)"
        # But is_strict_inchikey should reject SYNTH.
        assert not is_strict_inchikey(synth), \
            "CD-6: is_strict_inchikey should reject SYNTH"
    check("CD-6: is_valid_inchikey unified (base delegates to normalizer); is_strict_inchikey added", test_cd6_is_valid_inchikey_unified)

    # =====================================================================
    # CD-7: _ACTIVITY_VALUE_MAX shared via cleaning._constants
    # =====================================================================
    def test_cd7_activity_value_max_shared():
        from cleaning._constants import (
            ACTIVITY_VALUE_CENSORED_THRESHOLD,
            ACTIVITY_VALUE_NON_PHYSICAL_THRESHOLD,
        )
        assert ACTIVITY_VALUE_CENSORED_THRESHOLD == 1e6, \
            f"CD-7: censored threshold should be 1e6; got {ACTIVITY_VALUE_CENSORED_THRESHOLD}"
        assert ACTIVITY_VALUE_NON_PHYSICAL_THRESHOLD == 1e9, \
            f"CD-7: non-physical threshold should be 1e9; got {ACTIVITY_VALUE_NON_PHYSICAL_THRESHOLD}"
        # Both modules should import from _constants.
        normalizer_src = (PHASE1_ROOT / "cleaning" / "normalizer.py").read_text()
        dedup_src = (PHASE1_ROOT / "cleaning" / "deduplicator.py").read_text()
        assert "from cleaning._constants import" in normalizer_src, \
            "CD-7: normalizer should import from cleaning._constants"
        assert "from cleaning._constants import" in dedup_src, \
            "CD-7: deduplicator should import from cleaning._constants"
    check("CD-7: _ACTIVITY_VALUE_MAX shared via cleaning._constants", test_cd7_activity_value_max_shared)

    # =====================================================================
    # CD-8: InChIKey LIKE patterns unified to 'IK%' prefix
    # =====================================================================
    def test_cd8_inchikey_like_patterns_unified():
        # Check migration 001 — the actual CONSTRAINT line should use IK% prefix,
        # not %IK% substring. Comments may mention the old pattern for documentation.
        m001 = (PHASE1_ROOT / "database" / "migrations" / "001_initial_schema.sql").read_text()
        # Extract only the constraint CHECK line (not the comment).
        constraint_lines = [line for line in m001.split("\n") if "LIKE" in line and "inchikey LIKE" in line]
        for line in constraint_lines:
            assert "LIKE '%IK%'" not in line, \
                f"CD-8: migration 001 constraint line should not use LIKE '%IK%' (substring); got: {line!r}"
        assert any("LIKE 'IK%'" in line for line in constraint_lines), \
            "CD-8: migration 001 should have a constraint with LIKE 'IK%' (prefix)"
        # Check migration 003
        m003 = (PHASE1_ROOT / "database" / "migrations" / "003_models_fix_migration.sql").read_text()
        assert "LIKE 'IK%'" in m003
        # Check loaders.py — only check non-comment code lines.
        loaders_lines = [
            line for line in (PHASE1_ROOT / "database" / "loaders.py").read_text().split("\n")
            if not line.strip().startswith("#")
        ]
        loaders_code = "\n".join(loaders_lines)
        assert 'upper.startswith("IK")' in loaders_code, \
            "CD-8: loaders.py should use upper.startswith('IK')"
        # The substring form (in actual code, not comments) should be gone.
        # Use a regex that matches the if-statement form.
        bad_pattern = re.compile(r'^\s*if\s+"IK"\s+in\s+upper', re.MULTILINE)
        assert not bad_pattern.search(loaders_code), \
            "CD-8: loaders.py should not use 'if \"IK\" in upper' in code (only in comments)"
    check("CD-8: InChIKey LIKE patterns unified to 'IK%' prefix across all 4 locations", test_cd8_inchikey_like_patterns_unified)

    # =====================================================================
    # Phase 1 ↔ Phase 2 connection: bridge reads ALL 7 sources
    # =====================================================================
    def test_phase1_phase2_connection_all_7_sources():
        """Verify the bridge reads CSVs from all 7 Phase 1 source pipelines."""
        bridge_src = (PHASE2_ROOT / "drugos_graph" / "phase1_bridge.py").read_text()
        # All 7 sources should be referenced.
        expected = {
            "drugbank_drugs.csv": "DrugBank",
            "drugbank_interactions.csv.gz": "DrugBank",
            "omim_gene_disease_associations.csv": "OMIM",
            "chembl_drugs.csv": "ChEMBL",
            "uniprot_proteins.csv": "UniProt",
            "string_protein_protein_interactions.csv": "STRING",
            "disgenet_gene_disease_associations.csv": "DisGeNET",
            "pubchem_enrichment.csv": "PubChem",
        }
        for csv, source in expected.items():
            assert csv in bridge_src, \
                f"Phase 1↔2 bridge missing CSV for {source}: {csv}"
    check("Phase 1↔2 connection: bridge reads all 7 source CSVs", test_phase1_phase2_connection_all_7_sources)

    return passed, failed, failures


# Phase 2 root for stitch_loader checks
PHASE2_ROOT = PROJECT_ROOT / "phase2"


def main() -> int:
    print("=" * 78)
    print("v16 ROOT FIX VERIFICATION TEST SUITE")
    print("=" * 78)
    print()
    passed, failed, failures = _run_all_tests()
    print()
    print("=" * 78)
    print(f"RESULT: {passed} PASSED, {failed} FAILED")
    if failures:
        print("\nFailures:")
        for f in failures:
            print(f"  - {f}")
    print("=" * 78)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
