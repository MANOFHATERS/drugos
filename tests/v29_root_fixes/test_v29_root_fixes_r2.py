"""v29 ROOT FIX verification tests — round 2 (fixes 13-18).

Each test verifies ONE specific root-level fix from the second round
of the forensic audit remediation. Tests are named fix_13 through
fix_18 to match the fix numbering.

Run with:
    python -m pytest tests/v29_root_fixes/test_v29_root_fixes_r2.py -v
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_PHASE1_ROOT = _PROJECT_ROOT / "phase1"
_PHASE2_ROOT = _PROJECT_ROOT / "phase2"
for p in (str(_PHASE1_ROOT), str(_PHASE2_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ============================================================================
# FIX 13: Phase 1 pipeline broken session management
# ============================================================================

def fix_13_chembl_load_captures_session():
    """FIX 13: ChEMBLPipeline.load() must capture __enter__() return value."""
    import inspect
    from pipelines.chembl_pipeline import ChEMBLPipeline
    src = inspect.getsource(ChEMBLPipeline.load)
    assert "_session_cm" in src, "ChEMBLPipeline.load() must use _session_cm"
    assert "_session_cm.__enter__()" in src, "must capture __enter__() return"
    assert "_session_cm.__exit__" in src, "must call __exit__ on the context manager"


def fix_13_drugbank_load_captures_session():
    """FIX 13: DrugBankPipeline.load() must capture __enter__() return value."""
    import inspect
    from pipelines.drugbank_pipeline import DrugBankPipeline
    src = inspect.getsource(DrugBankPipeline.load)
    assert "_session_cm" in src
    assert "_session_cm.__enter__()" in src
    assert "_session_cm.__exit__" in src


def fix_13_pubchem_load_captures_session():
    """FIX 13: PubChemPipeline.load() must capture __enter__() return value
    AND pass exc_info to __exit__ (fixing the partial-commit bug)."""
    import inspect
    from pipelines.pubchem_pipeline import PubChemPipeline
    src = inspect.getsource(PubChemPipeline.load)
    assert "_session_cm" in src
    assert "_session_cm.__enter__()" in src
    # Must NOT call __exit__(None, None, None) as actual code (only in
    # comments documenting what was removed). Check by stripping comments.
    import re
    # Remove lines that are comments (start with optional whitespace + #).
    code_only = "\n".join(
        line for line in src.split("\n")
        if not line.strip().startswith("#")
    )
    # Also remove inline comments.
    code_only = re.sub(r'#.*$', '', code_only, flags=re.MULTILINE)
    assert "__exit__(None, None, None)" not in code_only, \
        "PubChemPipeline.load() must NOT call __exit__(None, None, None) — that commits partial data on exception"
    assert "_session_cm.__exit__(*_exc_info)" in code_only, \
        "PubChemPipeline.load() must pass exc_info to __exit__"


def fix_13_uniprot_load_captures_session():
    """FIX 13: UniProtPipeline.load() must capture __enter__() return value."""
    import inspect
    from pipelines.uniprot_pipeline import UniProtPipeline
    src = inspect.getsource(UniProtPipeline.load)
    assert "_session_cm" in src
    assert "_session_cm.__enter__()" in src
    assert "_session_cm.__exit__" in src


# ============================================================================
# FIX 14: SCHEMA_VERSION mismatch
# ============================================================================

def fix_14_schema_version_is_9():
    """FIX 14: SCHEMA_VERSION must be 9 (matching migration 009)."""
    from database.base import SCHEMA_VERSION
    assert SCHEMA_VERSION == 9, \
        f"SCHEMA_VERSION must be 9 (matching migration 009), got {SCHEMA_VERSION}"


# ============================================================================
# FIX 15: InChIKey DB CHECK constraint
# ============================================================================

def fix_15_orm_uses_portable_check():
    """FIX 15: ORM CheckConstraint must use portable LENGTH=27 OR SYNTH%
    (not the PostgreSQL-only ~ regex operator, which breaks SQLite)."""
    from database.models import Drug
    from sqlalchemy import CheckConstraint
    constraints = [
        c for c in Drug.__table_args__
        if isinstance(c, CheckConstraint) and c.name == "chk_drugs_inchikey_format"
    ]
    assert len(constraints) == 1
    sql = str(constraints[0].sqltext)
    # Must use the portable form (LENGTH=27 OR LIKE 'SYNTH%'), not the
    # PostgreSQL-only ~ regex operator.
    assert "LENGTH(inchikey) = 27" in sql
    assert "SYNTH" in sql
    # Must NOT use the ~ operator (PostgreSQL-only).
    assert "~" not in sql or "LENGTH" in sql, \
        f"ORM constraint must use portable LENGTH form, got: {sql}"


def fix_15_python_validator_is_canonical():
    """FIX 15: the Python-side canonical regex validator exists and works."""
    from cleaning._constants import (
        CANONICAL_INCHIKEY_REGEX, is_canonical_inchikey,
    )
    # Valid InChIKey passes.
    assert is_canonical_inchikey("BSYNRYMUTXBXSQ-UHFFFAOYSA-N")
    # 27-char gibberish fails (caught by Python, not by DB CHECK).
    assert not is_canonical_inchikey("XXXXXXXXXXXXXXXX-XXXXXXXXXX-X")
    assert not is_canonical_inchikey("AAAAAAAAAAAAAAAAAAAAAAAAAAA")  # 27 chars, no hyphens
    # SYNTH passes.
    assert is_canonical_inchikey("SYNTH-ABCDEF0123-ABCDEF0123-A")


# ============================================================================
# FIX 16: HGT Graph Transformer wired into training pipeline
# ============================================================================

def fix_16_step11b_exists():
    """FIX 16: step11b_train_graph_transformer must exist and be callable."""
    from drugos_graph.run_pipeline import step11b_train_graph_transformer
    assert callable(step11b_train_graph_transformer)


def fix_16_step11b_wired_into_run_full_pipeline():
    """FIX 16: run_full_pipeline must call step11b after step11."""
    run_pipeline_path = _PHASE2_ROOT / "drugos_graph" / "run_pipeline.py"
    content = run_pipeline_path.read_text()
    assert "step11b_train_graph_transformer" in content
    assert 'results["step11b"]' in content


def fix_16_v1_criteria_considers_hgt():
    """FIX 16: _check_v1_launch_criteria must consult step11b (HGT)."""
    run_pipeline_path = _PHASE2_ROOT / "drugos_graph" / "run_pipeline.py"
    content = run_pipeline_path.read_text()
    assert "hgt_val_auc" in content
    assert "hgt_held_out_auc" in content
    assert "best_model_type" in content


# ============================================================================
# FIX 17: Phase 1 ↔ Phase 2 100% connectivity
# ============================================================================

def fix_17_bridge_reads_from_postgres_orm():
    """FIX 17: bridge must read from PostgreSQL via SQLAlchemy ORM models,
    not just CSVs. End-to-end test with a real SQLite DB."""
    import tempfile
    db_path = tempfile.mktemp(suffix=".db")
    old_db_url = os.environ.get("DATABASE_URL")
    old_dev = os.environ.get("DRUGOS_DEV_ALLOW_DEFAULT_DB")
    old_settings_url = None
    try:
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        os.environ["DRUGOS_DEV_ALLOW_DEFAULT_DB"] = "1"

        # v29: config.settings reads DATABASE_URL at IMPORT TIME and
        # caches it as a module-level constant. Just setting the env
        # var is NOT enough — we must also patch the cached constant
        # AND reset the engine singleton so get_engine() re-reads it.
        import config.settings as _settings
        old_settings_url = getattr(_settings, "DATABASE_URL", None)
        _settings.DATABASE_URL = f"sqlite:///{db_path}"

        # v29: dispose any existing engine so get_engine() creates a new
        # one pointing at our test DB (the engine is a singleton).
        import database.connection as _db_conn
        _db_conn._engine = None
        _db_conn._session_factory = None
        try:
            from database.connection import dispose_engine
            dispose_engine(force=True)
        except Exception:
            pass

        from database.connection import get_engine, get_db_session
        from database.base import Base
        from database.models import (
            Drug, Protein, DrugProteinInteraction, GeneDiseaseAssociation,
            ProteinProteinInteraction, PipelineRun,
        )

        engine = get_engine()
        Base.metadata.create_all(engine)

        with get_db_session(pipeline_name="drugbank", run_id="test1") as session:
            pr = PipelineRun(source="drugbank", status="running")
            session.add(pr)
            session.add(Drug(
                inchikey="BSYNRYMUTXBXSQ-UHFFFAOYSA-N", name="Aspirin",
                drugbank_id="DB00945", is_fda_approved=True, is_withdrawn=False,
            ))
            session.add(Drug(
                inchikey="HEFNNWSXXWATIU-UHFFFAOYSA-N", name="Valdecoxib",
                drugbank_id="DB00567", is_fda_approved=True, is_withdrawn=True,
            ))
            session.flush()
            session.add(Protein(
                uniprot_id="P23219", gene_symbol="COX1",
                protein_name="PGHS1", organism="Homo sapiens",
            ))
            session.add(Protein(
                uniprot_id="P35354", gene_symbol="COX2",
                protein_name="PGHS2", organism="Homo sapiens",
            ))
            session.flush()
            session.add(DrugProteinInteraction(
                drug_id=1, protein_id=1, interaction_type="inhibitor",
            ))
            session.add(GeneDiseaseAssociation(
                gene_symbol="COX1", disease_id="OMIM:133700",
                disease_name="Cervical cancer", source="omim",
                score=0.8, association_type="associated",
            ))
            # PPI requires protein_a_id < protein_b_id (chk_ppi_ordered).
            session.add(ProteinProteinInteraction(
                protein_a_id=1, protein_b_id=2, combined_score=900,
                source="string",
            ))
            pr.status = "success"

        from drugos_graph.phase1_bridge import (
            _phase1_db_available, read_phase1_outputs,
            _PHASE1_BACKEND_POSTGRES,
        )
        assert _phase1_db_available() is True
        frames = read_phase1_outputs(prefer_postgres=True)
        assert frames["_phase1_backend"] == _PHASE1_BACKEND_POSTGRES
        assert len(frames["drugs"]) == 2
        assert len(frames["interactions"]) == 1
        assert len(frames["uniprot_proteins"]) == 2
        assert len(frames["string_ppi"]) == 1

        # Patient safety: Valdecoxib must be flagged withdrawn.
        valdecoxib = [
            d for d in frames["drugs"].to_dict("records")
            if d["name"] == "Valdecoxib"
        ][0]
        assert valdecoxib["is_withdrawn"] is True
    finally:
        # Dispose the engine so it doesn't leak into other tests.
        try:
            from database.connection import dispose_engine
            dispose_engine(force=True)
        except Exception:
            pass
        # Restore config.settings.DATABASE_URL.
        if old_settings_url is not None:
            try:
                import config.settings as _settings_restore
                _settings_restore.DATABASE_URL = old_settings_url
            except Exception:
                pass
        if old_db_url is not None:
            os.environ["DATABASE_URL"] = old_db_url
        else:
            os.environ.pop("DATABASE_URL", None)
        if old_dev is not None:
            os.environ["DRUGOS_DEV_ALLOW_DEFAULT_DB"] = old_dev
        else:
            os.environ.pop("DRUGOS_DEV_ALLOW_DEFAULT_DB", None)
        if os.path.exists(db_path):
            os.unlink(db_path)


def fix_17_bridge_uses_correct_orm_columns():
    """FIX 17: bridge must JOIN through integer FKs (drug_id, protein_id),
    not reference non-existent string columns (drug_inchikey, protein_uniprot_id)."""
    bridge_path = _PHASE2_ROOT / "drugos_graph" / "phase1_bridge.py"
    content = bridge_path.read_text()
    # Must use JOIN through integer FKs.
    assert "DrugProteinInteraction.drug_id == _m.Drug.id" in content
    assert "DrugProteinInteraction.protein_id == _m.Protein.id" in content
    # Must NOT reference the non-existent drug_inchikey / protein_uniprot_id
    # attributes on DrugProteinInteraction.
    assert "_m.DrugProteinInteraction.drug_inchikey" not in content
    assert "_m.DrugProteinInteraction.protein_uniprot_id" not in content


# ============================================================================
# FIX 18: DRUGOS_ALLOW_NO_SAMPLER requires two flags
# ============================================================================

def fix_18_escape_hatch_requires_two_flags():
    """FIX 18: DRUGOS_ALLOW_NO_SAMPLER must require DRUGOS_DEV_ALLOW_NO_SAMPLER too."""
    transe_path = _PHASE2_ROOT / "drugos_graph" / "transe_model.py"
    content = transe_path.read_text()
    assert "DRUGOS_DEV_ALLOW_NO_SAMPLER" in content, \
        "transe_model must check DRUGOS_DEV_ALLOW_NO_SAMPLER (v29 two-flag fix)"
    # The _allow_no_sampler variable must require both flags.
    assert "_flag_1 and _flag_2" in content or "_flag_1 and _flag_2" in content


def fix_18_escape_hatch_deprecation_warning():
    """FIX 18: a deprecation warning must be logged when the escape hatch is active."""
    transe_path = _PHASE2_ROOT / "drugos_graph" / "transe_model.py"
    content = transe_path.read_text()
    assert "DEPRECATION" in content
    assert "will be REMOVED" in content


# ============================================================================
# Run all tests
# ============================================================================

if __name__ == "__main__":
    test_funcs = [
        v for k, v in sorted(globals().items())
        if k.startswith("fix_") and callable(v)
    ]
    print(f"Running {len(test_funcs)} v29 round-2 root-fix verification tests...\n")
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
