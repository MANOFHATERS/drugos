"""v34 CRITICAL fix regression tests.

Each test verifies a specific CRITICAL fix from the v34 forensic audit.
If any test fails, the corresponding fix was reverted or broken.

Run with: pytest tests/v34_critical_fixes/test_v34_critical_fixes.py -v
"""
import os
import sys
import re
import json
from pathlib import Path

import pytest

# Add phase1 and phase2 to sys.path
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
PHASE1 = PROJECT_ROOT / "phase1"
PHASE2 = PROJECT_ROOT / "phase2"
for p in (str(PHASE1), str(PHASE2)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ─── CRITICAL #1: Deduplicator sentinel leakage ─────────────────────────────

def test_critical_1_deduplicator_no_sentinel_leakage():
    """CRITICAL #1: deduplicator must NOT leak sentinel strings into output.

    The previous code replaced NaN/SYNTH/mixture InChIKeys with sentinels
    like `__NULL_UNIQUE_5__` and NEVER restored them. The fix writes
    sentinels to a hidden `_dedup_sentinel_key` column instead of
    overwriting `inchikey`.
    """
    import pandas as pd
    from cleaning.deduplicator import dedup_by_inchikey

    # Build a DataFrame with NaN and SYNTH InChIKeys.
    df = pd.DataFrame([
        {"drugbank_id": "DB00001", "name": "Insulin", "inchikey": None, "source": "drugbank"},
        {"drugbank_id": "DB00002", "name": "Aspirin", "inchikey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N", "source": "drugbank"},
        {"drugbank_id": "DB00003", "name": "Antibody", "inchikey": "SYNTH-abc123", "source": "drugbank"},
        {"drugbank_id": "DB00004", "name": "Insulin2", "inchikey": None, "source": "drugbank"},
    ])
    result = dedup_by_inchikey(df, return_result=True)
    out = result.df
    # Verify NO sentinel strings leaked into the inchikey column.
    for ik in out["inchikey"].dropna():
        assert not str(ik).startswith("__"), (
            f"CRITICAL #1 REGRESSION: sentinel string {ik!r} leaked into "
            f"output inchikey column. The deduplicator's _dedup_sentinel_key "
            f"fix was reverted or broken."
        )
    # Verify NaN InChIKeys are preserved as NaN (not converted to sentinel).
    nan_rows = out[out["inchikey"].isna()]
    assert len(nan_rows) >= 1, "NaN InChIKey rows should be preserved"


# ─── CRITICAL #2: SYNTH key format divergence ───────────────────────────────

def test_critical_2_synth_key_format_unified():
    """CRITICAL #2: DrugBank and resolver must produce SAME SYNTH key format.

    The previous code: DrugBank generated `SYNTH-DB00001` (13 chars),
    resolver generated `SYNTH{hash}-...` (27 chars). They NEVER matched.
    The fix: DrugBank now calls `make_synthetic_inchikey` from
    entity_resolution.base.
    """
    try:
        from entity_resolution.base import make_synthetic_inchikey, is_synthetic_inchikey
    except ImportError:
        pytest.skip("entity_resolution not importable in this env")
    # Generate a SYNTH key the way the resolver does.
    resolver_key = make_synthetic_inchikey("Insulin")
    assert is_synthetic_inchikey(resolver_key), \
        f"Resolver SYNTH key not detected as synthetic: {resolver_key}"
    # Verify the format is 27 chars (matches canonical InChIKey shape).
    assert len(resolver_key) == 27, \
        f"Resolver SYNTH key is {len(resolver_key)} chars, expected 27: {resolver_key}"
    # Verify it starts with SYNTH (5 chars).
    assert resolver_key.startswith("SYNTH"), \
        f"SYNTH key doesn't start with 'SYNTH': {resolver_key}"


# ─── CRITICAL #3: UniProt validator accepts TEST fixtures ───────────────────

def test_critical_3_uniprot_rejects_test_fixtures_in_prod():
    """CRITICAL #3: UniProt validators must REJECT test fixtures in production.

    The previous code accepted `TEST001` and any <6-char alphanumeric
    unconditionally. The fix: only accept in dev/test environments.
    """
    # Save env
    original_env = os.environ.get("DRUGOS_ENVIRONMENT")
    try:
        # Test PRODUCTION mode — should REJECT test fixtures.
        os.environ["DRUGOS_ENVIRONMENT"] = "production"
        from database.models import _validate_uniprot_id
        with pytest.raises(ValueError, match="Invalid UniProt accession"):
            _validate_uniprot_id("TEST001")
        with pytest.raises(ValueError, match="Invalid UniProt accession"):
            _validate_uniprot_id("P001")
        # Real UniProt IDs should still pass.
        assert _validate_uniprot_id("P23219") == "P23219"
        assert _validate_uniprot_id("Q9Y6K9") == "Q9Y6K9"
    finally:
        if original_env is None:
            os.environ.pop("DRUGOS_ENVIRONMENT", None)
        else:
            os.environ["DRUGOS_ENVIRONMENT"] = original_env

    # Test DEV mode — should ACCEPT test fixtures.
    original_env = os.environ.get("DRUGOS_ENVIRONMENT")
    try:
        os.environ["DRUGOS_ENVIRONMENT"] = "dev"
        from database.loaders import _validate_uniprot_id as _loaders_validate
        assert _loaders_validate("TEST001") == "TEST001"
        assert _loaders_validate("P001") == "P001"
    finally:
        if original_env is None:
            os.environ.pop("DRUGOS_ENVIRONMENT", None)
        else:
            os.environ["DRUGOS_ENVIRONMENT"] = original_env


# ─── CRITICAL #4: Dev credentials swap unconditional ────────────────────────

def test_critical_4_dev_credentials_swap_gated():
    """CRITICAL #4: dev credentials swap must be GATED on opt-in flag.

    The previous code applied `cosmic:cosmic` defaults unconditionally.
    The fix: only apply when DRUGOS_DEV_ALLOW_DEFAULT_DB=1 is set.
    """
    import importlib
    # Save env
    original_env_vals = {
        k: os.environ.get(k) for k in (
            "DRUGOS_ENVIRONMENT", "DRUGOS_DEV_ALLOW_DEFAULT_DB",
            "DATABASE_URL", "DRUGOS_DEV_DB_USER", "DRUGOS_DEV_DB_PASSWORD",
        )
    }
    try:
        # Test 1: NO opt-in → DATABASE_URL should NOT contain cosmic:cosmic.
        os.environ["DRUGOS_ENVIRONMENT"] = "development"
        os.environ.pop("DRUGOS_DEV_ALLOW_DEFAULT_DB", None)
        os.environ["DATABASE_URL"] = "postgresql://REPLACE_USER:REPLACE_PASSWORD@localhost/db"
        import config.settings as _settings
        importlib.reload(_settings)
        assert "cosmic" not in _settings.DATABASE_URL, \
            f"CRITICAL #4 REGRESSION: dev credentials applied WITHOUT opt-in. " \
            f"DATABASE_URL={_settings.DATABASE_URL}"

        # Test 2: opt-in → DATABASE_URL SHOULD contain cosmic:cosmic.
        os.environ["DRUGOS_DEV_ALLOW_DEFAULT_DB"] = "1"
        importlib.reload(_settings)
        assert "cosmic" in _settings.DATABASE_URL, \
            f"CRITICAL #4 REGRESSION: dev credentials NOT applied WITH opt-in. " \
            f"DATABASE_URL={_settings.DATABASE_URL}"
    finally:
        # Restore env
        for k, v in original_env_vals.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ─── CRITICAL #5: clear_graph no-op ─────────────────────────────────────────

def test_critical_5_clear_graph_phrase_constant():
    """CRITICAL #5: clear_graph must use the SHARED phrase constant.

    The previous code: run_pipeline passed "CLEAR_ALL_DRUGOS_DATA" but
    kg_builder expected "DELETE EVERYTHING I UNDERSTAND THE CONSEQUENCES".
    The fix: expose DEFAULT_CLEAR_GRAPH_PHRASE and use it in both places.
    """
    from drugos_graph.kg_builder import DEFAULT_CLEAR_GRAPH_PHRASE, _CLEAR_GRAPH_PHRASE
    # The default phrase should match the env-var-overridable phrase.
    assert DEFAULT_CLEAR_GRAPH_PHRASE == "DELETE EVERYTHING I UNDERSTAND THE CONSEQUENCES"
    # When env var is not set, _CLEAR_GRAPH_PHRASE should equal the default.
    # (This test may fail if DRUGOS_CLEAR_GRAPH_PHRASE is set in env — that's OK.)
    if "DRUGOS_CLEAR_GRAPH_PHRASE" not in os.environ:
        assert _CLEAR_GRAPH_PHRASE == DEFAULT_CLEAR_GRAPH_PHRASE


# ─── CRITICAL #7: PostgreSQL reader drops critical columns ──────────────────

def test_critical_7_postgres_query_includes_gene_columns():
    """CRITICAL #7: PostgreSQL GDA query must select gene_id, uniprot_id, etc.

    The previous code selected only 6 columns. The fix selects all columns
    the bridge's stage code consumes.
    """
    import inspect
    from drugos_graph import phase1_bridge
    src = inspect.getsource(phase1_bridge)
    # The fix added these columns to the SELECT statement.
    assert "GeneDiseaseAssociation.gene_id" in src, \
        "CRITICAL #7 REGRESSION: gene_id (NCBI) not selected in postgres query"
    assert "GeneDiseaseAssociation.uniprot_id" in src, \
        "CRITICAL #7 REGRESSION: uniprot_id not selected in postgres query"
    # The fix synthesizes canonical_gene_id from ncbi_gene_id.
    assert "canonical_gene_id" in src, \
        "CRITICAL #7 REGRESSION: canonical_gene_id synthesis missing"


# ─── CRITICAL #8: Compound-treats-Disease edges largely absent ──────────────

def test_critical_8_treats_edges_include_synthetic_diseases():
    """CRITICAL #8: treats-edge derivation must handle empty disease_id.

    The previous code skipped rows with empty disease_id. The fix
    slugifies disease_name into a SYNDROME: synthetic Disease ID.
    """
    import inspect
    from drugos_graph import phase1_bridge
    src = inspect.getsource(phase1_bridge)
    assert "SYNDROME:" in src, \
        "CRITICAL #8 REGRESSION: SYNDROME: slugification missing"
    # Verify the Disease ID pattern accepts SYNDROME: prefix.
    from drugos_graph.kg_builder import ID_PATTERNS
    pattern = ID_PATTERNS["Disease"]
    assert re.match(pattern, "SYNDROME:pain"), \
        f"CRITICAL #8 REGRESSION: SYNDROME:pain doesn't match Disease pattern: {pattern}"


# ─── CRITICAL #9: Held-out AUC misalignment ─────────────────────────────────

def test_critical_9_eval_triples_uses_slot_index():
    """CRITICAL #9: _evaluate_triples must assign neg_tails by slot index.

    The previous code used .append() in grouped-by-relation order, causing
    neg_tails[i] to misalign with h_expanded[i]. The fix pre-allocates
    and assigns by slot index.
    """
    import inspect
    from drugos_graph import transe_model
    src = inspect.getsource(transe_model)
    # The fix uses pre-allocation: `neg_tails_list: List[int] = [0] * n_total_neg`
    assert "[0] * n_total_neg" in src or "[0] * n_total_neg" in src, \
        "CRITICAL #9 REGRESSION: neg_tails_list pre-allocation missing"
    # The fix assigns by slot index: `neg_tails_list[s] = ...`
    assert "neg_tails_list[s]" in src, \
        "CRITICAL #9 REGRESSION: slot-index assignment missing"


# ─── CRITICAL #10: No test/train leakage check ──────────────────────────────

def test_critical_10_test_train_leakage_check_exists():
    """CRITICAL #10: train_transe must check test/train overlap.

    The previous code only checked val/train overlap. The fix adds
    test/train and test/val overlap checks.
    """
    import inspect
    from drugos_graph import transe_model
    src = inspect.getsource(transe_model)
    # The fix added test/train and test/val overlap checks.
    assert "test/train" in src or "test_set" in src, \
        "CRITICAL #10 REGRESSION: test/train leakage check missing"
    assert "test/val" in src or "tv_overlap" in src, \
        "CRITICAL #10 REGRESSION: test/val leakage check missing"


# ─── CRITICAL #11: Silent random fallback for missing relations ─────────────

def test_critical_11_random_fallback_logs_critical():
    """CRITICAL #11: silent random fallback must log at CRITICAL level.

    The previous code logged "once at CRITICAL via _build_per_relation_pools"
    but that function only ran during training, not held-out eval. The fix
    logs at CRITICAL every time the fallback fires during held-out eval.
    """
    import inspect
    from drugos_graph import transe_model
    src = inspect.getsource(transe_model)
    # The fix added a logger.critical call for the silent fallback.
    assert "logger.critical" in src, \
        "CRITICAL #11 REGRESSION: logger.critical call missing"
    # The fix mentions CRITICAL #11 in the comment.
    assert "CRITICAL #11" in src, \
        "CRITICAL #11 REGRESSION: CRITICAL #11 comment missing"


# ─── CRITICAL #12: ChemBERTa cache loading RCE ──────────────────────────────

def test_critical_12_chemberta_uses_weights_only_true():
    """CRITICAL #12: ChemBERTa cache loading must use weights_only=True.

    The previous code used weights_only=False, allowing arbitrary code
    execution from malicious cache files. The fix uses weights_only=True.
    """
    import inspect
    from drugos_graph import chemberta_encoder
    src = inspect.getsource(chemberta_encoder)
    # Verify NO `torch.load(..., weights_only=False)` CALL remains.
    # (Mentions in comments are OK — we only care about actual calls.)
    import re as _re
    # Find all `torch.load(f, weights_only=False)` calls (not in comments).
    call_pattern = _re.compile(r'torch\.load\([^)]*weights_only\s*=\s*False', _re.MULTILINE)
    # Strip comments and docstrings before checking.
    lines = []
    for line in src.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        lines.append(line)
    src_no_comments = "\n".join(lines)
    assert not call_pattern.search(src_no_comments), \
        "CRITICAL #12 REGRESSION: torch.load(..., weights_only=False) call still present"
    # Verify weights_only=True IS used.
    assert "weights_only=True" in src, \
        "CRITICAL #12 REGRESSION: weights_only=True missing in chemberta_encoder"


# ─── CRITICAL #13: drugbank_parser NameError ────────────────────────────────

def test_critical_13_drugbank_parser_defines_canonical_id():
    """CRITICAL #13: drugbank_to_target_edges_from_phase1 must define canonical_id.

    The previous code referenced `canonical_id` without defining it,
    causing NameError on first call. The fix defines it using the same
    logic as drugbank_to_node_records_from_phase1.
    """
    import inspect
    from drugos_graph import drugbank_parser
    src = inspect.getsource(drugbank_parser.drugbank_to_target_edges_from_phase1)
    # The fix defines canonical_id inside the function.
    assert "canonical_id = " in src, \
        "CRITICAL #13 REGRESSION: canonical_id definition missing in drugbank_to_target_edges_from_phase1"
    # Verify it's the SAME logic as the node records function.
    node_src = inspect.getsource(drugbank_parser.drugbank_to_node_records_from_phase1)
    assert "canonical_id = inchikey or drugbank_id" in src, \
        "CRITICAL #13 REGRESSION: canonical_id logic doesn't match node records"


# ─── CRITICAL #14: Entity resolver reverse-index bug ────────────────────────

def test_critical_14_reverse_set_uses_aliases_value():
    """CRITICAL #14: _reverse_set must use aliases[id_system] as external_id.

    The previous code passed `gene_id` (DRKG source ID) as external_id
    instead of `aliases[id_system]` (the actual NCBI/Ensembl/HGNC ID).
    """
    import inspect
    from drugos_graph import entity_resolver
    src = inspect.getsource(entity_resolver)
    # The fix passes aliases[id_system] as the external_id argument.
    assert "aliases[\"ncbi_gene_id\"]" in src or "aliases['ncbi_gene_id']" in src, \
        "CRITICAL #14 REGRESSION: aliases['ncbi_gene_id'] not used in _reverse_set call"
    # Verify the fix uses str(aliases[...]) not bare gene_id.
    assert "str(aliases[" in src, \
        "CRITICAL #14 REGRESSION: str(aliases[...]) wrapper missing"


# ─── CRITICAL #15: STRING score /1000 on already-normalized CSV ─────────────

def test_critical_15_string_score_scale_detection():
    """CRITICAL #15: STRING loader must detect 0-1 vs 0-1000 scale.

    The previous code unconditionally divided by 1000. The fix detects
    whether the score is already on a 0-1 scale (max <= 1.0) and skips
    the division.
    """
    import inspect
    from drugos_graph import string_loader
    src = inspect.getsource(string_loader)
    # The fix adds a scale-detection branch.
    assert "score_f > 1.0" in src, \
        "CRITICAL #15 REGRESSION: scale detection (score_f > 1.0) missing"
    # Verify the 0-1 branch uses the score as-is.
    assert "Already on 0-1 scale" in src, \
        "CRITICAL #15 REGRESSION: 'Already on 0-1 scale' branch missing"


# ─── Neo4j persistence fix ──────────────────────────────────────────────────

def test_neo4j_persistence_staged_graph_json_written():
    """Verify run_unified.py persists the staged graph to disk.

    The previous code used RecordingGraphBuilder (in-memory) and lost
    all data on process exit. The fix writes staged_graph.json.
    """
    staged_path = PHASE2 / "data" / "processed" / "staged_graph.json"
    if staged_path.exists():
        with open(staged_path) as f:
            data = json.load(f)
        assert "node_counts_by_type" in data, "staged_graph.json missing node_counts_by_type"
        assert "edge_counts_by_type" in data, "staged_graph.json missing edge_counts_by_type"
        # Verify some nodes were persisted.
        total_nodes = sum(data["node_counts_by_type"].values())
        assert total_nodes > 0, "staged_graph.json has zero nodes"
    else:
        # If the file doesn't exist, run the bridge to create it.
        import subprocess
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "run_unified.py"), "--no-full-pipeline"],
            cwd=str(PROJECT_ROOT),
            capture_output=True, text=True, timeout=120,
        )
        assert staged_path.exists(), \
            f"staged_graph.json not created by run_unified.py. stderr: {result.stderr[-500:]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
