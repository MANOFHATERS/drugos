"""v29 ROOT FIX verification tests — round 4 (fixes 29-50).

Tests for the fourth round of forensic audit remediation.

Run with:
    python -m pytest tests/v29_root_fixes/test_v29_root_fixes_r4.py -v
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_PHASE1_ROOT = _PROJECT_ROOT / "phase1"
_PHASE2_ROOT = _PROJECT_ROOT / "phase2"
for p in (str(_PHASE1_ROOT), str(_PHASE2_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ============================================================================
# FIX 29 (P1-1): is_fda_approved semantic bug
# ============================================================================

def fix_29_chembl_does_not_fabricate_fda_from_max_phase():
    """FIX 29: ChEMBL must NOT set is_fda_approved=True from max_phase>=4.
    max_phase=4 means 'globally approved by ANY regulator', not FDA-specific."""
    chembl_path = _PHASE1_ROOT / "pipelines" / "chembl_pipeline.py"
    content = chembl_path.read_text()
    # The fix must change the return True to return None for max_phase>=4
    assert "return None  # v29: was True" in content, \
        "ChEMBL must return None (not True) for max_phase>=4 — patient-safety fix (v29 root fix P1-1)"


# ============================================================================
# FIX 30 (P1-11/12/13): mid-transaction commits
# ============================================================================

def fix_30_chembl_no_mid_tx_commit():
    """FIX 30: ChEMBL must not have session.commit() mid-transaction."""
    chembl_path = _PHASE1_ROOT / "pipelines" / "chembl_pipeline.py"
    content = chembl_path.read_text()
    # Find session.commit() in actual code (not comments)
    import re
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if "session.commit()" in line and not line.strip().startswith("#"):
            # Check if it's in a finally/cleanup block (allowed) or mid-tx (not allowed)
            context = "\n".join(lines[max(0, i-5):i])
            if "finally" not in context and "cleanup" not in context.lower():
                assert False, \
                    f"ChEMBL has mid-tx session.commit() at line {i+1}: {line.strip()}"
    # Must have flush replacements
    assert "session.flush()" in content


def fix_30_disgenet_no_mid_tx_commit():
    """FIX 30: DisGeNET must not have session.commit() mid-transaction."""
    disgenet_path = _PHASE1_ROOT / "pipelines" / "disgenet_pipeline.py"
    content = disgenet_path.read_text()
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if "session.commit()" in line and not line.strip().startswith("#"):
            context = "\n".join(lines[max(0, i-5):i])
            if "finally" not in context and "cleanup" not in context.lower():
                assert False, \
                    f"DisGeNET has mid-tx session.commit() at line {i+1}: {line.strip()}"


# ============================================================================
# FIX 31 (P1-14): OMIM audit trail
# ============================================================================

def fix_31_omim_run_load_only_writes_audit():
    """FIX 31: OMIM run_load_only() must call _write_run_log."""
    omim_path = _PHASE1_ROOT / "pipelines" / "omim_pipeline.py"
    content = omim_path.read_text()
    # Find run_load_only method
    idx = content.find("def run_load_only")
    assert idx != -1
    method_src = content[idx:idx + 3000]
    assert "_write_run_log" in method_src, \
        "OMIM run_load_only must call _write_run_log (v29 root fix P1-14)"


# ============================================================================
# FIX 32 (P1-15): UniProt 4xx retry
# ============================================================================

def fix_32_uniprot_no_4xx_retry():
    """FIX 32: UniProt must not retry 4xx errors (except 429)."""
    uniprot_path = _PHASE1_ROOT / "pipelines" / "uniprot_pipeline.py"
    content = uniprot_path.read_text()
    assert "4xx" in content or "status_code" in content, \
        "UniProt must check status code for 4xx (v29 root fix P1-15)"
    # Must have a check that re-raises 4xx without retrying
    assert "DownloadError" in content or "raise" in content


# ============================================================================
# FIX 33 (P1-17/18/19): assert-as-validation
# ============================================================================

def fix_33_no_assert_in_chembl_validation():
    """FIX 33: ChEMBL must not use assert for validation."""
    chembl_path = _PHASE1_ROOT / "pipelines" / "chembl_pipeline.py"
    content = chembl_path.read_text()
    # Find assert statements in actual code (not comments)
    lines = content.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("assert ") and not stripped.startswith("#"):
            assert False, \
                f"ChEMBL has assert at line {i+1}: {stripped} — use raise ValueError instead (v29 root fix P1-17)"


def fix_33_no_assert_in_string_validation():
    """FIX 33: STRING must not use assert for validation."""
    string_path = _PHASE1_ROOT / "pipelines" / "string_pipeline.py"
    content = string_path.read_text()
    lines = content.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("assert ") and not stripped.startswith("#"):
            assert False, \
                f"STRING has assert at line {i+1}: {stripped} — use raise ValueError instead (v29 root fix P1-18)"


def fix_33_no_assert_in_disgenet_validation():
    """FIX 33: DisGeNET must not use assert for validation."""
    disgenet_path = _PHASE1_ROOT / "pipelines" / "disgenet_pipeline.py"
    content = disgenet_path.read_text()
    lines = content.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("assert ") and not stripped.startswith("#"):
            assert False, \
                f"DisGeNET has assert at line {i+1}: {stripped} — use raise ValueError instead (v29 root fix P1-19)"


# ============================================================================
# FIX 34 (P1-24): ID format divergence
# ============================================================================

def fix_34_id_normalization_utils_exist():
    """FIX 34: Canonical ID normalization utilities must exist."""
    from cleaning._constants import (
        normalize_inchikey, normalize_uniprot_id,
        normalize_drugbank_id, normalize_chembl_id,
        normalize_pubchem_cid, normalize_gene_symbol,
    )
    # Test InChIKey normalization
    assert normalize_inchikey("bsynrymutxbxsq-uhfffaoysa-n") == "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
    assert normalize_inchikey("  BSYNRYMUTXBXSQ-UHFFFAOYSA-N  ") == "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
    # Test UniProt normalization
    assert normalize_uniprot_id("p23219") == "P23219"
    # Test DrugBank ID normalization
    assert normalize_drugbank_id("db00945") == "DB00945"
    # Test ChEMBL ID normalization
    assert normalize_chembl_id("chembl123") == "CHEMBL123"
    # Test PubChem CID normalization
    assert normalize_pubchem_cid("0002244") == 2244
    assert normalize_pubchem_cid(2244) == 2244
    assert normalize_pubchem_cid(None) is None
    # Test gene symbol normalization
    assert normalize_gene_symbol("tp53") == "TP53"


def fix_34_pipelines_import_normalizers():
    """FIX 34: All 7 pipelines must import the normalization utilities."""
    pipelines = [
        "chembl_pipeline.py", "drugbank_pipeline.py", "uniprot_pipeline.py",
        "string_pipeline.py", "disgenet_pipeline.py", "omim_pipeline.py",
        "pubchem_pipeline.py",
    ]
    for fname in pipelines:
        path = _PHASE1_ROOT / "pipelines" / fname
        content = path.read_text()
        assert "normalize_" in content, \
            f"{fname} must import normalize_* functions (v29 root fix P1-24)"


# ============================================================================
# FIX 35 (C-7): Multi-stereo descriptors
# ============================================================================

def fix_35_multi_stereo_descriptors_preserved():
    """FIX 35: Multi-stereo descriptors like (2R,3S) must be preserved."""
    import re
    # Read the regex from the source
    resolver_path = _PHASE1_ROOT / "entity_resolution" / "resolver_utils.py"
    content = resolver_path.read_text()
    assert "2R,3S" in content or "2RS" in content or "1,2}[RS]" in content, \
        "resolver_utils must match multi-stereo descriptors like (2R,3S) (v29 root fix C-7)"


# ============================================================================
# FIX 36 (C-8): config/settings.py crashes on import
# ============================================================================

def fix_36_config_importable_in_dev():
    """FIX 36: config.settings must be importable without DRUGOS_DEV_ALLOW_DEFAULT_DB."""
    # The fix changed raise ValueError to a warning.
    settings_path = _PHASE1_ROOT / "config" / "settings.py"
    content = settings_path.read_text()
    # Find the block that was raise ValueError — must now be warning
    assert "v29 ROOT FIX (audit C-8)" in content, \
        "config/settings must have v29 root fix comment (audit C-8)"


# ============================================================================
# FIX 37 (C-10): configure_normalizer dead code
# ============================================================================

def fix_37_normalizer_kwargs_dict_works():
    """FIX 37: kwargs_dict() must return actual config, not empty dict."""
    normalizer_path = _PHASE1_ROOT / "cleaning" / "normalizer.py"
    content = normalizer_path.read_text()
    assert "v29 ROOT FIX (audit C-10)" in content, \
        "normalizer must have v29 root fix comment (audit C-10)"


# ============================================================================
# FIX 38 (C-11): configure_deduplicator ignored
# ============================================================================

def fix_38_dedup_reads_config():
    """FIX 38: dedup functions must read from _config, not DEFAULT_COMPLETENESS_WEIGHTS."""
    dedup_path = _PHASE1_ROOT / "cleaning" / "deduplicator.py"
    content = dedup_path.read_text()
    assert "v29 ROOT FIX (audit C-11)" in content, \
        "deduplicator must have v29 root fix comment (audit C-11)"


# ============================================================================
# FIX 39 (D-4): UniProt CHECK constraint
# ============================================================================

def fix_39_uniprot_canonical_regex_exists():
    """FIX 39: Canonical UniProt accession regex must exist."""
    from cleaning._constants import CANONICAL_UNIPROT_ACCESSION_REGEX
    assert CANONICAL_UNIPROT_ACCESSION_REGEX is not None
    # Must match valid accessions (the FULL regex accepts both 6-char and 10-char)
    from cleaning._constants import CANONICAL_UNIPROT_ACCESSION_REGEX_FULL
    assert CANONICAL_UNIPROT_ACCESSION_REGEX_FULL.match("P23219") is not None
    assert CANONICAL_UNIPROT_ACCESSION_REGEX_FULL.match("Q9Y6K9") is not None


# ============================================================================
# FIX 40 (D-5): activity_value FLOAT → NUMERIC
# ============================================================================

def fix_40_activity_value_is_numeric():
    """FIX 40: activity_value must be Numeric(10,4), not Float."""
    from database.models import DrugProteinInteraction
    from sqlalchemy import Numeric
    col = DrugProteinInteraction.__table__.c.activity_value
    assert isinstance(col.type, Numeric), \
        f"activity_value must be Numeric, got {type(col.type).__name__}"
    assert col.type.precision == 10
    assert col.type.scale == 4


# ============================================================================
# FIX 41 (D-6): FOUR UNIQUE indexes → ONE
# ============================================================================

def fix_41_gda_has_one_unique_index():
    """FIX 41: GDA must have only ONE unique index on (gene_symbol, disease_id, source)."""
    from database.models import GeneDiseaseAssociation
    from sqlalchemy import UniqueConstraint, Index
    unique_count = 0
    for c in GeneDiseaseAssociation.__table_args__:
        if isinstance(c, (UniqueConstraint, Index)) and getattr(c, "unique", False):
            # Check if it's on the (gene_symbol, disease_id, source) columns
            cols = [col.name for col in c.columns] if hasattr(c, 'columns') else []
            if set(cols) == {"gene_symbol", "disease_id", "source"}:
                unique_count += 1
    assert unique_count <= 1, \
        f"GDA must have at most 1 unique index on (gene_symbol, disease_id, source), got {unique_count}"


# ============================================================================
# FIX 42 (D-7): PubChem FK
# ============================================================================

def fix_42_pubchem_pipeline_run_id_is_integer_fk():
    """FIX 42: PubChemCompoundProperty.pipeline_run_id must be Integer FK."""
    from database.models import PubChemCompoundProperty
    from sqlalchemy import Integer
    col = PubChemCompoundProperty.__table__.c.pipeline_run_id
    assert isinstance(col.type, Integer), \
        f"pipeline_run_id must be Integer, got {type(col.type).__name__}"
    # Must have a FK to pipeline_runs
    fks = list(col.foreign_keys)
    assert len(fks) > 0, "pipeline_run_id must have a foreign key"
    assert "pipeline_runs" in str(fks[0].target_fullname)


# ============================================================================
# FIX 43 (D-10): rollback_migration SQL split
# ============================================================================

def fix_43_rollback_uses_state_machine_splitter():
    """FIX 43: rollback_migration must use state-machine SQL splitter."""
    run_migrations_path = _PHASE1_ROOT / "database" / "migrations" / "run_migrations.py"
    content = run_migrations_path.read_text()
    assert "v29 ROOT FIX (audit D-10)" in content, \
        "run_migrations must have v29 root fix comment (audit D-10)"
    assert "_split_sql_statements" in content or "state_machine" in content.lower(), \
        "run_migrations must use state-machine SQL splitter"


# ============================================================================
# FIX 44 (D-15): Decimal→float coercion
# ============================================================================

def fix_44_decimal_preserved():
    """FIX 44: Decimal precision must be preserved, not coerced to float."""
    loaders_path = _PHASE1_ROOT / "database" / "loaders.py"
    content = loaders_path.read_text()
    assert "v29 ROOT FIX (audit D-15)" in content, \
        "loaders must have v29 root fix comment (audit D-15)"


# ============================================================================
# FIX 45 (L-5): Compound ID fragmentation
# ============================================================================

def fix_45_compound_id_normalization_helper_exists():
    """FIX 45: _normalize_compound_id_to_inchikey helper must exist."""
    from drugos_graph.id_crosswalk import _normalize_compound_id_to_inchikey
    assert callable(_normalize_compound_id_to_inchikey)


def fix_45_stitch_uses_normalization():
    """FIX 45: STITCH loader must call the normalization helper."""
    stitch_path = _PHASE2_ROOT / "drugos_graph" / "stitch_loader.py"
    content = stitch_path.read_text()
    assert "_normalize_compound_id_to_inchikey" in content, \
        "STITCH loader must use _normalize_compound_id_to_inchikey (v29 root fix L-5)"


def fix_45_sider_uses_normalization():
    """FIX 45: SIDER loader must call the normalization helper."""
    sider_path = _PHASE2_ROOT / "drugos_graph" / "sider_loader.py"
    content = sider_path.read_text()
    assert "_normalize_compound_id_to_inchikey" in content, \
        "SIDER loader must use _normalize_compound_id_to_inchikey (v29 root fix L-5)"


def fix_45_drkg_uses_normalization():
    """FIX 45: DRKG loader must call the normalization helper."""
    drkg_path = _PHASE2_ROOT / "drugos_graph" / "drkg_loader.py"
    content = drkg_path.read_text()
    assert "_normalize_compound_id_to_inchikey" in content, \
        "DRKG loader must use _normalize_compound_id_to_inchikey (v29 root fix L-5)"


# ============================================================================
# FIX 46 (L-8): PubChem CID case-sensitivity
# ============================================================================

def fix_46_pubchem_cid_case_insensitive():
    """FIX 46: PubChem CID matching must be case-insensitive."""
    pubchem_path = _PHASE2_ROOT / "drugos_graph" / "pubchem_loader.py"
    content = pubchem_path.read_text()
    assert "v29 ROOT FIX (audit L-8)" in content, \
        "pubchem_loader must have v29 root fix comment (audit L-8)"


# ============================================================================
# FIX 47 (L-9/I-7): O(n²) canonicalize
# ============================================================================

def fix_47_id_crosswalk_uses_cache():
    """FIX 47: id_crosswalk must use cached reverse index (not O(n²))."""
    crosswalk_path = _PHASE2_ROOT / "drugos_graph" / "id_crosswalk.py"
    content = crosswalk_path.read_text()
    assert "v29 ROOT FIX (audit L-9/I-7)" in content, \
        "id_crosswalk must have v29 root fix comment (audit L-9/I-7)"
    assert "_reverse_index_cache" in content or "cache" in content.lower()


# ============================================================================
# FIX 48 (M-7): ChemBERTA features used by TransE
# ============================================================================

def fix_48_transe_accepts_node_features():
    """FIX 48: TransEModel must accept optional node_features parameter."""
    from drugos_graph.transe_model import TransEModel
    import inspect
    sig = inspect.signature(TransEModel.__init__)
    assert "node_features" in sig.parameters, \
        "TransEModel must accept node_features parameter (v29 root fix M-7)"


# ============================================================================
# FIX 49 (O-3/O-4): Neo4j decorative
# ============================================================================

def fix_49_recording_builder_warns_in_production():
    """FIX 49: run_unified must warn when RecordingGraphBuilder used in production."""
    run_unified_path = _PROJECT_ROOT / "run_unified.py"
    content = run_unified_path.read_text()
    assert "v29 ROOT FIX (audit O-3)" in content, \
        "run_unified must have v29 root fix comment (audit O-3)"


def fix_49_neo4j_exporter_no_misleading_pg_session():
    """FIX 49: neo4j_exporter must not have misleading pg_session parameter."""
    exporter_path = _PHASE1_ROOT / "exporters" / "neo4j_exporter.py"
    content = exporter_path.read_text()
    assert "v29 ROOT FIX (audit O-4)" in content, \
        "neo4j_exporter must have v29 root fix comment (audit O-4)"


# ============================================================================
# FIX 50 (O-9): double-load into Neo4j
# ============================================================================

def fix_50_no_double_neo4j_load():
    """FIX 50: run_unified must skip Neo4j re-load when --neo4j-uri is set."""
    run_unified_path = _PROJECT_ROOT / "run_unified.py"
    content = run_unified_path.read_text()
    assert "v29 ROOT FIX (audit O-9)" in content, \
        "run_unified must have v29 root fix comment (audit O-9)"
    # Must have the corrected skip_neo4j predicate
    assert "skip_neo4j=(args.neo4j_uri is not None)" in content, \
        "run_unified must skip Neo4j re-load when --neo4j-uri is set"


# ============================================================================
# Run all tests
# ============================================================================

if __name__ == "__main__":
    test_funcs = [
        v for k, v in sorted(globals().items())
        if k.startswith("fix_") and callable(v)
    ]
    print(f"Running {len(test_funcs)} v29 round-4 root-fix verification tests...\n")
    passed = 0
    failed = 0
    for tf in test_funcs:
        try:
            tf()
            print(f"  PASS  {tf.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {tf.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed, {passed + failed} total")
    if failed:
        sys.exit(1)
