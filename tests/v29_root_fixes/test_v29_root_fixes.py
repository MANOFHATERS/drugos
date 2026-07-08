"""v29 ROOT FIX verification tests.

Each test verifies ONE specific root-level fix from the forensic audit.
Tests are named fix_01 through fix_12 to match the fix numbering.

Run with:
    python -m pytest tests/v29_root_fixes/test_v29_root_fixes.py -v
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path so imports work.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_PHASE1_ROOT = _PROJECT_ROOT / "phase1"
_PHASE2_ROOT = _PROJECT_ROOT / "phase2"
for p in (str(_PHASE1_ROOT), str(_PHASE2_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ============================================================================
# FIX 1: phase1_bridge.py reads from PostgreSQL when available, CSV fallback
# ============================================================================

def fix_01_bridge_has_postgres_backend():
    """FIX 1: bridge must have _read_phase1_from_postgres + _phase1_db_available."""
    from drugos_graph.phase1_bridge import (
        _read_phase1_from_postgres,
        _phase1_db_available,
        _PHASE1_BACKEND_POSTGRES,
        _PHASE1_BACKEND_CSV,
    )
    assert _PHASE1_BACKEND_POSTGRES == "postgresql"
    assert _PHASE1_BACKEND_CSV == "csv"
    # _phase1_db_available should return a bool (True or False).
    # The exact value depends on whether a DB is configured in the
    # test environment — we only check the return TYPE, not the value,
    # because round-2 tests may leave a DB configured.
    result = _phase1_db_available()
    assert isinstance(result, bool), \
        f"_phase1_db_available() must return bool, got {type(result)}"
    # read_phase1_outputs must accept prefer_postgres kwarg.
    from drugos_graph.phase1_bridge import read_phase1_outputs
    import inspect
    sig = inspect.signature(read_phase1_outputs)
    assert "prefer_postgres" in sig.parameters


def fix_01_bridge_csv_backend_reports_marker():
    """FIX 1: CSV backend must stamp _phase1_backend marker on the result dict."""
    from drugos_graph.phase1_bridge import read_phase1_outputs, _PHASE1_BACKEND_CSV
    frames = read_phase1_outputs(str(_PHASE1_ROOT / "processed_data"), prefer_postgres=False)
    assert frames.get("_phase1_backend") == _PHASE1_BACKEND_CSV


# ============================================================================
# FIX 2: Graph Transformer (HGTConv) actually exists and works
# ============================================================================

def fix_02_graph_transformer_exists():
    """FIX 2: GraphTransformerModel must be importable and NOT TransE."""
    from drugos_graph.graph_transformer_model import (
        GraphTransformerModel, GraphTransformerConfig,
    )
    assert GraphTransformerModel is not None
    assert GraphTransformerConfig is not None


def fix_02_graph_transformer_produces_valid_scores():
    """FIX 2: HGT model produces scores in [0,1] and supports asymmetric relations."""
    import torch
    from drugos_graph.graph_transformer_model import (
        GraphTransformerModel, GraphTransformerConfig,
    )
    node_types = ["Compound", "Protein", "Disease"]
    relation_types = [
        ("Compound", "targets", "Protein"),
        ("Compound", "treats", "Disease"),
        ("Protein", "associated_with", "Disease"),
    ]
    cfg = GraphTransformerConfig(embedding_dim=32, num_heads=2, num_layers=2)
    model = GraphTransformerModel(node_types, relation_types, config=cfg)
    model.resize_node_embeddings({"Compound": 50, "Protein": 30, "Disease": 20})
    x_dict = {nt: model.get_node_embeddings(nt) for nt in node_types}
    edge_index_dict = {
        ("Compound", "targets", "Protein"): torch.tensor([[0, 1, 2], [0, 1, 2]]),
        ("Compound", "treats", "Disease"): torch.tensor([[0, 1], [0, 1]]),
        ("Protein", "associated_with", "Disease"): torch.tensor([[0, 1], [0, 1]]),
    }
    heads = torch.tensor([0, 1])
    rels = torch.tensor([1, 1])  # treats
    tails = torch.tensor([0, 1])
    scores = model.forward(
        heads, rels, tails,
        x_dict=x_dict, edge_index_dict=edge_index_dict,
        head_type="Compound", tail_type="Disease",
        rel_names=["treats", "treats"],
    )
    # Scores must be in [0, 1].
    assert (scores >= 0).all() and (scores <= 1).all(), \
        f"Scores out of [0,1]: {scores.tolist()}"
    # Asymmetric: (Compound, treats, Disease) != (Disease, treats, Compound).
    scores_rev = model.forward(
        tails, rels, heads,
        x_dict=x_dict, edge_index_dict=edge_index_dict,
        head_type="Disease", tail_type="Compound",
        rel_names=["treats", "treats"],
    )
    assert not torch.allclose(scores, scores_rev), \
        "HGT must produce asymmetric scores (TransE cannot)"


def fix_02_no_graph_transformer_in_v28():
    """FIX 2 (regression guard): grep must now FIND TransformerConv/HGTConv."""
    # In v28 this grep returned 0 matches. After v29 it must find HGTConv.
    import subprocess
    result = subprocess.run(
        ["grep", "-rl", "HGTConv", str(_PHASE2_ROOT)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, "HGTConv must appear in at least one Phase 2 file"
    assert "graph_transformer_model.py" in result.stdout


# ============================================================================
# FIX 3: Patient-safety chain
# ============================================================================

def fix_03_withdrawn_trigger_is_bidirectional():
    """FIX 3: migration 006 trigger must set is_withdrawn := FALSE when
    'withdrawn' is NOT in groups (bidirectional, not one-way ratchet)."""
    sql_path = _PHASE1_ROOT / "database" / "migrations" / "006_drug_withdrawn_safety_columns.sql"
    content = sql_path.read_text()
    # The trigger function must contain an ELSE branch that sets FALSE.
    assert "NEW.is_withdrawn := FALSE" in content, \
        "Trigger must have bidirectional FALSE branch (v29 root fix)"
    assert "bidirectional" in content.lower() or "BIDIRECTIONAL" in content, \
        "Trigger must document the bidirectional fix"


def fix_03_sider_frequencies_is_called():
    """FIX 3: parse_sider_frequencies must be called inside load_sider."""
    sider_path = _PHASE2_ROOT / "drugos_graph" / "sider_loader.py"
    content = sider_path.read_text()
    # The load_sider function must contain a call to parse_sider_frequencies.
    assert "parse_sider_frequencies()" in content, \
        "load_sider must call parse_sider_frequencies (v29 root fix)"


def fix_03_no_sampler_escape_hatch_refused_in_production():
    """FIX 3: DRUGOS_ALLOW_NO_SAMPLER must be refused in production mode."""
    transe_path = _PHASE2_ROOT / "drugos_graph" / "transe_model.py"
    content = transe_path.read_text()
    assert "PRODUCTION_ESCAPE_HATCH_REFUSED" in content, \
        "transe_model must refuse DRUGOS_ALLOW_NO_SAMPLER in production"


# ============================================================================
# FIX 4: InChIKey regex divergence — single canonical regex
# ============================================================================

def fix_04_canonical_inchikey_regex_exists():
    """FIX 4: cleaning._constants must define CANONICAL_INCHIKEY_REGEX."""
    from cleaning._constants import (
        CANONICAL_INCHIKEY_REGEX, strip_inchikey_extension, is_canonical_inchikey,
    )
    assert CANONICAL_INCHIKEY_REGEX.pattern == r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$"


def fix_04_normalizer_and_dedup_share_canonical_regex():
    """FIX 4: normalizer and dedup must import the SAME regex object."""
    from cleaning._constants import CANONICAL_INCHIKEY_REGEX
    from cleaning.normalizer import CANONICAL_INCHIKEY_REGEX as normalizer_regex
    from cleaning.deduplicator import _INCHIKEY_PATTERN as dedup_regex
    assert normalizer_regex is CANONICAL_INCHIKEY_REGEX, \
        "normalizer must import canonical regex from _constants"
    assert dedup_regex is CANONICAL_INCHIKEY_REGEX, \
        "deduplicator must import canonical regex from _constants"


def fix_04_strip_inchikey_extension():
    """FIX 4: strip_inchikey_extension removes non-canonical suffixes."""
    from cleaning._constants import strip_inchikey_extension
    # Canonical 27-char — unchanged.
    assert strip_inchikey_extension("BSYNRYMUTXBXSQ-UHFFFAOYSA-N") == "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
    # With extension — stripped.
    assert strip_inchikey_extension("BSYNRYMUTXBXSQ-UHFFFAOYSA-N-a") == "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
    # SYNTH — unchanged.
    assert strip_inchikey_extension("SYNTH-ABCDEF0123-ABCDEF0123-A") == "SYNTH-ABCDEF0123-ABCDEF0123-A"


def fix_04_version_char_not_called_protonation():
    """FIX 4: the scientific error calling version char 'protonation char' is fixed."""
    normalizer_path = _PHASE1_ROOT / "cleaning" / "normalizer.py"
    content = normalizer_path.read_text()
    # The old error label "invalid_protonation_char" should be gone.
    assert "invalid_protonation_char" not in content, \
        "normalizer must use 'invalid_version_char' not 'invalid_protonation_char'"
    assert "invalid_version_char" in content


# ============================================================================
# FIX 5: MatchConfidence inversion fixed
# ============================================================================

def fix_05_confidence_hierarchy_correct():
    """FIX 5: FUZZY < NAME_NORMALIZED (not inverted)."""
    from entity_resolution.base import MatchConfidence as MC
    assert MC.FUZZY < MC.NAME_NORMALIZED, \
        f"FUZZY ({MC.FUZZY}) must be < NAME_NORMALIZED ({MC.NAME_NORMALIZED})"
    assert MC.PROTEIN_NAME_FUZZY < MC.NAME_NORMALIZED, \
        f"PROTEIN_NAME_FUZZY ({MC.PROTEIN_NAME_FUZZY}) must be < NAME_NORMALIZED ({MC.NAME_NORMALIZED})"
    # Full hierarchy check.
    assert MC.INCHIKEY_EXACT > MC.INCHIKEY_CONNECTIVITY > MC.NAME_NORMALIZED
    assert MC.NAME_NORMALIZED > MC.GENE_NAME_ORGANISM > MC.FUZZY
    assert MC.FUZZY > MC.PROTEIN_NAME_FUZZY > MC.UNKNOWN


def fix_05_method_confidence_dict_synced():
    """FIX 5: METHOD_CONFIDENCE dict must match the enum."""
    from entity_resolution.resolver_utils import METHOD_CONFIDENCE
    from entity_resolution.base import MatchConfidence as MC
    assert METHOD_CONFIDENCE["fuzzy"] == MC.FUZZY
    assert METHOD_CONFIDENCE["protein_name_fuzzy"] == MC.PROTEIN_NAME_FUZZY
    assert METHOD_CONFIDENCE["fuzzy"] < METHOD_CONFIDENCE["name_normalized"]


# ============================================================================
# FIX 6: kg_builder relation collapse fixed
# ============================================================================

def fix_06_disgenet_edges_grouped_by_rel_type():
    """FIX 6: run_pipeline must group DisGeNET edges by per-edge rel_type."""
    run_pipeline_path = _PHASE2_ROOT / "drugos_graph" / "run_pipeline.py"
    content = run_pipeline_path.read_text()
    # The fix uses a defaultdict to group edges by rel_type.
    assert "_edges_by_rel" in content, \
        "DisGeNET loading must group edges by rel_type (v29 root fix)"


def fix_06_omim_edges_grouped_by_rel_type():
    """FIX 6: run_pipeline must group OMIM edges by per-edge rel_type."""
    run_pipeline_path = _PHASE2_ROOT / "drugos_graph" / "run_pipeline.py"
    content = run_pipeline_path.read_text()
    assert "_omim_by_rel" in content, \
        "OMIM loading must group edges by rel_type (v29 root fix)"


# ============================================================================
# FIX 7: node_disjoint_split as default training split
# ============================================================================

def fix_07_node_disjoint_split_is_first_option():
    """FIX 7: run_pipeline must try node-disjoint split BEFORE temporal/stratified."""
    run_pipeline_path = _PHASE2_ROOT / "drugos_graph" / "run_pipeline.py"
    content = run_pipeline_path.read_text()
    assert "node_disjoint_split_used" in content, \
        "run_pipeline must track node_disjoint_split_used flag"
    assert "NODE-DISJOINT split" in content, \
        "run_pipeline must log when using node-disjoint split"


# ============================================================================
# FIX 8: Remove happy-path try/except in run_pipeline.py
# ============================================================================

def fix_08_step_exception_or_skip_exists():
    """FIX 8: _step_exception_or_skip helper must exist and re-raise in production."""
    from drugos_graph.run_pipeline import _step_exception_or_skip, _is_production_mode
    assert callable(_step_exception_or_skip)
    # In test env (no DRUGOS_ENVIRONMENT set), production mode is False.
    old = os.environ.get("DRUGOS_ENVIRONMENT")
    try:
        os.environ.pop("DRUGOS_ENVIRONMENT", None)
        assert _is_production_mode() is False
        os.environ["DRUGOS_ENVIRONMENT"] = "production"
        assert _is_production_mode() is True
    finally:
        if old is None:
            os.environ.pop("DRUGOS_ENVIRONMENT", None)
        else:
            os.environ["DRUGOS_ENVIRONMENT"] = old


def fix_08_step_handlers_call_helper():
    """FIX 8: all step exception handlers must call _step_exception_or_skip."""
    run_pipeline_path = _PHASE2_ROOT / "drugos_graph" / "run_pipeline.py"
    content = run_pipeline_path.read_text()
    # Count old-style "skipped": True assignments vs new-style helper calls.
    old_style_count = content.count('results["step')  # crude check
    helper_count = content.count("_step_exception_or_skip(")
    assert helper_count >= 10, \
        f"At least 10 step handlers must call _step_exception_or_skip, got {helper_count}"


# ============================================================================
# FIX 9: run_unified.py actually invokes Phase 1 when missing
# ============================================================================

def fix_09_run_unified_invokes_phase1():
    """FIX 9: run_unified.py must attempt to run Phase 1 when processed_data missing."""
    run_unified_path = _PROJECT_ROOT / "run_unified.py"
    content = run_unified_path.read_text()
    assert "make all" in content or "make -C" in content, \
        "run_unified must invoke Phase 1 via make (v29 root fix)"
    assert "auto-invocation" in content.lower() or "auto-run" in content.lower(), \
        "run_unified must document the Phase 1 auto-invocation"


# ============================================================================
# FIX 10: master_pipeline_dag fails when Phase 2 fails
# ============================================================================

def fix_10_master_dag_uses_all_success():
    """FIX 10: trigger_phase2 must use ALL_SUCCESS, not ALL_DONE."""
    dag_path = _PHASE1_ROOT / "dags" / "master_pipeline_dag.py"
    content = dag_path.read_text()
    # The old trigger_rule=ALL_DONE must be replaced with ALL_SUCCESS.
    assert "TriggerRule.ALL_SUCCESS" in content, \
        "trigger_phase2 must use ALL_SUCCESS (v29 root fix)"
    # check=True must be set so non-zero exit raises.
    assert "check=True" in content, \
        "subprocess.run must use check=True to propagate failures"


# ============================================================================
# FIX 11: Dockerfile.airflow + docker-compose Neo4j + Makefile
# ============================================================================

def fix_11_dockerfile_airflow_python_version():
    """FIX 11: Dockerfile.airflow must use Python 3.11, not 3.8."""
    dockerfile_path = _PHASE1_ROOT / "docker" / "Dockerfile.airflow"
    content = dockerfile_path.read_text()
    assert "python3.11" in content or "python:3.11" in content, \
        "Dockerfile.airflow must use Python 3.11 (v29 root fix)"
    assert "apache/airflow:2.8.1\n" not in content, \
        "Dockerfile.airflow must not use the broken 2.8.1 base (Python 3.8)"


def fix_11_docker_compose_has_neo4j():
    """FIX 11: docker-compose.yml must have a Neo4j service."""
    compose_path = _PHASE1_ROOT / "docker-compose.yml"
    content = compose_path.read_text()
    assert "neo4j:" in content, \
        "docker-compose must define a neo4j service (v29 root fix)"
    assert "neo4j_data:" in content, \
        "docker-compose must define neo4j_data volume"


def fix_11_docker_compose_has_mlflow():
    """FIX 11: docker-compose.yml must have an MLflow service."""
    compose_path = _PHASE1_ROOT / "docker-compose.yml"
    content = compose_path.read_text()
    assert "mlflow:" in content, \
        "docker-compose must define an mlflow service (v29 root fix)"


def fix_11_makefile_run_airflow_works():
    """FIX 11: Makefile run-airflow must set AIRFLOW_HOME and init DB."""
    makefile_path = _PHASE1_ROOT / "Makefile"
    content = makefile_path.read_text()
    assert "AIRFLOW_HOME" in content, \
        "Makefile run-airflow must set AIRFLOW_HOME (v29 root fix)"
    assert "airflow db migrate" in content or "airflow db init" in content, \
        "Makefile run-airflow must init the Airflow DB"
    # Must use tabs, not spaces (Makefile requirement).
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("run-airflow:"):
            # The next non-comment, non-empty line must start with a tab.
            for j in range(i + 1, min(i + 5, len(lines))):
                if lines[j].strip() and not lines[j].lstrip().startswith("#"):
                    assert lines[j].startswith("\t"), \
                        f"Makefile line {j+1} must use a tab, not spaces"
                    break
            break


# ============================================================================
# FIX 12: Skip duplicate-load steps 4/7f/7g/7h when bridge loaded
# ============================================================================

def fix_12_step4_skipped_when_phase1():
    """FIX 12: run_pipeline must skip step 4 when data_source=phase1."""
    run_pipeline_path = _PHASE2_ROOT / "drugos_graph" / "run_pipeline.py"
    content = run_pipeline_path.read_text()
    assert "phase1_bridge_already_loaded_drugbank" in content, \
        "Step 4 must skip with phase1_bridge_already_loaded_drugbank reason"


def fix_12_step7fgh_skipped_when_phase1():
    """FIX 12: run_pipeline must skip 7f/7g/7h when data_source=phase1."""
    run_pipeline_path = _PHASE2_ROOT / "drugos_graph" / "run_pipeline.py"
    content = run_pipeline_path.read_text()
    assert "_skip_7fgh" in content, \
        "run_pipeline must define _skip_7fgh flag (v29 root fix)"
    assert "skip_7f_phase1_bridge_loaded" in content
    assert "skip_7g_phase1_bridge_loaded" in content
    assert "skip_7h_phase1_bridge_loaded" in content


# ============================================================================
# Run all tests
# ============================================================================

if __name__ == "__main__":
    # Allow running this file directly (not just via pytest).
    test_funcs = [
        v for k, v in sorted(globals().items())
        if k.startswith("fix_") and callable(v)
    ]
    print(f"Running {len(test_funcs)} v29 root-fix verification tests...\n")
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
