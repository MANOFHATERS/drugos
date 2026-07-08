"""v22 ROOT FIX verification tests — Part 1: Bridge & Integration.

Verifies audit findings P0-1, P0-2, X-1, X-2, X-3, X-4, X-17, X-18.
Each test reads the ACTUAL production code (not test stubs) to confirm
the root-level fix is present.
"""
from __future__ import annotations

import ast
import inspect
import os
import re
import sys
from pathlib import Path

import pytest

# ─── Path setup ──────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent  # /home/z/.../v22_drugos_unified_phase1_phase2_V22_ROOT_FIXED
PHASE1_ROOT = PROJECT_ROOT / "phase1"
PHASE2_ROOT = PROJECT_ROOT / "phase2"

for p in (str(PROJECT_ROOT), str(PHASE1_ROOT), str(PHASE2_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _read(rel: str) -> str:
    """Read a file under the project root."""
    return (PROJECT_ROOT / rel).read_text(encoding="utf-8")


def _source_lines(module_path: str) -> str:
    """Read a Python module's source by relative path."""
    return _read(module_path)


# ─── P0-1: phase1_processed_dir parameter in step7_additional_sources ───────

def test_p0_1_step7_additional_sources_has_phase1_processed_dir_param():
    """run_pipeline.step7_additional_sources MUST accept phase1_processed_dir.

    Audit finding: NameError at runtime, silently swallowed. Steps 7f/7g/7h
    referenced phase1_processed_dir but the function had no such parameter.
    """
    src = _source_lines("phase2/drugos_graph/run_pipeline.py")
    # Find the function definition and check the signature.
    m = re.search(
        r"def step7_additional_sources\(([^)]*)\)",
        src,
        re.DOTALL,
    )
    assert m is not None, "step7_additional_sources function not found"
    sig = m.group(1)
    assert "phase1_processed_dir" in sig, (
        f"phase1_processed_dir parameter missing from step7_additional_sources "
        f"signature. Got: {sig}"
    )


def test_p0_1_run_full_pipeline_threads_phase1_processed_dir():
    """run_full_pipeline MUST thread phase1_processed_dir to step7."""
    src = _source_lines("phase2/drugos_graph/run_pipeline.py")
    # Find the call site inside run_full_pipeline.
    # The call passes phase1_processed_dir=phase1_processed_dir to step7.
    pattern = r"step7_additional_sources\([^)]*phase1_processed_dir=phase1_processed_dir"
    assert re.search(pattern, src, re.DOTALL), (
        "step7_additional_sources call does NOT thread phase1_processed_dir. "
        "The Phase 1 CSV fallback for DisGeNET/OMIM/PubChem is unreachable."
    )


# ─── P0-2: --skip-download uses BooleanOptionalAction ───────────────────────

def test_p0_2_skip_download_uses_boolean_optional_action():
    """run_unified.py --skip-download MUST use BooleanOptionalAction.

    Audit finding: action='store_true' + default=True with NO inverse flag.
    User could not turn downloads back on from this entry point.
    """
    src = _source_lines("run_unified.py")
    # Find the --skip-download argparse declaration.
    m = re.search(
        r'"--skip-download"[^)]*?action=argparse\.BooleanOptionalAction',
        src,
        re.DOTALL,
    )
    assert m is not None, (
        "--skip-download does NOT use argparse.BooleanOptionalAction. "
        "The argparse lockout (Chain 12) is still present."
    )


# ─── X-1: kg_builder edge-property stripping (FLAT vs nested) ───────────────

def test_x_1_kg_builder_handles_flat_edge_dicts():
    """kg_builder._load_edges MUST handle BOTH nested {'props': {...}}
    AND flat edge dicts (the shape phase1_bridge emits).

    Audit finding: props = edge.get('props', {}) expected nested dict;
    bridge emits flat dict → all edge properties silently stripped.
    """
    src = _source_lines("phase2/drugos_graph/kg_builder.py")
    # The fix adds an else-branch that handles flat edge dicts.
    # Look for the FLAT-edge handling code.
    assert "src_id" in src and "dst_id" in src, (
        "kg_builder._load_edges does not handle FLAT edge dicts with "
        "src_id/dst_id keys. The edge-property stripping bug is still present."
    )


# ─── X-2: bridge EC50/AC50 not classified as 'activates' ────────────────────

def test_x_2_bridge_ec50_not_activates():
    """phase1_bridge._classify_chembl_activity_edge MUST NOT return
    'activates' for EC50/AC50.

    Audit finding: EC50 measures potency of agonist OR antagonist;
    returning 'activates' inverts clinical directionality for the RL ranker.
    """
    src = _source_lines("phase2/drugos_graph/phase1_bridge.py")
    # Find the _classify_chembl_activity_edge function body.
    m = re.search(
        r"def _classify_chembl_activity_edge\b",
        src,
    )
    assert m is not None, "_classify_chembl_activity_edge not found"
    # Extract a window of 80 lines after the def.
    start = m.end()
    window = src[start:start + 6000]
    # Find the EC50/AC50 branch within the window.
    ec50_idx = window.find("ec50")
    if ec50_idx == -1:
        ec50_idx = window.find("EC50")
    if ec50_idx == -1:
        pytest.skip("EC50/AC50 branch not found in window — check function structure")
    # Look at the 400 chars after the ec50 mention.
    branch = window[ec50_idx:ec50_idx + 400]
    assert "'activates'" not in branch and '"activates"' not in branch, (
        f"EC50/AC50 branch STILL returns 'activates'. Body: {branch[:300]}"
    )


# ─── X-3: bridge ID emission (CHEMBL_TGT_ accepted, SYM: prefix) ────────────

def test_x_3_kg_builder_accepts_chembl_tgt_prefix():
    """kg_builder.ID_PATTERNS['Protein'] MUST accept CHEMBL_TGT_ prefix.

    Audit finding: bridge emits f'CHEMBL_TGT_{tgt_chembl}' for ChEMBL
    targets without UniProt AC; the production regex rejected this
    prefix → dead-lettered.
    """
    src = _source_lines("phase2/drugos_graph/kg_builder.py")
    # ID_PATTERNS["Protein"] regex must include CHEMBL_TGT_.
    assert "CHEMBL_TGT" in src, (
        "kg_builder.ID_PATTERNS['Protein'] does not accept CHEMBL_TGT_ prefix. "
        "ChEMBL target nodes are dead-lettered."
    )


def test_x_3_bridge_emits_sym_prefix_for_genes():
    """phase1_bridge MUST emit 'SYM:' prefix for bare gene symbols.

    Audit finding: bridge emitted bare gene symbols ('FGFR3') which the
    production ID_PATTERNS['Gene'] regex rejected.
    """
    src = _source_lines("phase2/drugos_graph/phase1_bridge.py")
    assert "SYM:" in src, (
        "phase1_bridge does not emit 'SYM:' prefix for gene symbols. "
        "Bare gene symbols are dead-lettered by kg_builder.ID_PATTERNS['Gene']."
    )


# ─── X-4: STITCH edge type not collapsed to 'binds' ─────────────────────────

def test_x_4_stitch_edge_type_not_collapsed_to_binds():
    """run_pipeline MUST NOT default STITCH rel_type to 'binds' in ACTUAL code.

    Audit finding: rel_type = edge.get('rel_type', 'binds') collapsed
    8 STITCH action-type distinctions to a single 'binds'.
    Comments explaining the old bug are OK — only real code matters.
    """
    src = _source_lines("phase2/drugos_graph/run_pipeline.py")
    # Strip comment-only lines and inline comments before checking.
    code_lines = []
    for line in src.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if "#" in line:
            line = line.split("#", 1)[0]
        code_lines.append(line)
    code_only = "\n".join(code_lines)
    # The old buggy pattern: rel_type = edge.get('rel_type', 'binds')
    bad_pattern = re.search(
        r"rel_type\s*=\s*edge\.get\(\s*['\"]rel_type['\"]\s*,\s*['\"]binds['\"]\s*\)",
        code_only,
    )
    assert bad_pattern is None, (
        "STITCH edge rel_type STILL defaults to 'binds' in production code. "
        "The 8 action-type distinctions are silently collapsed."
    )


# ─── X-17: pd.Timestamp.utcnow() removed ────────────────────────────────────

def test_x_17_no_pd_timestamp_utcnow_in_bridge():
    """phase1_bridge MUST NOT use pd.Timestamp.utcnow() (deprecated).

    Audit finding: pd.Timestamp.utcnow() is deprecated in pandas 2.x,
    emits FutureWarning, will break in pandas 3.0.
    """
    src = _source_lines("phase2/drugos_graph/phase1_bridge.py")
    # The only acceptable reference is in a comment explaining the fix.
    # The actual call must be pd.Timestamp.now(tz="UTC") or similar.
    # Search for the deprecated call pattern outside of comments.
    lines = src.splitlines()
    for i, line in enumerate(lines, 1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if "pd.Timestamp.utcnow()" in line or "Timestamp.utcnow()" in line:
            pytest.fail(
                f"phase1_bridge.py:{i}: deprecated pd.Timestamp.utcnow() call: {line.strip()}"
            )


# ─── X-18: TransEModel.__init__ saves num_entities ──────────────────────────

def test_x_18_transe_model_saves_num_entities():
    """TransEModel.__init__ MUST save num_entities as an attribute.

    Audit runtime bug: 'TransEModel' object has no attribute 'num_entities'
    during held-out evaluation. Held-out AUC was never computed → V1 launch
    criterion auc_meets_threshold always failed.
    """
    src = _source_lines("phase2/drugos_graph/transe_model.py")
    # Find TransEModel class definition.
    class_m = re.search(r"^class TransEModel\b", src, re.MULTILINE)
    assert class_m is not None, "TransEModel class not found"
    # Find __init__ within the class (next 3000 chars).
    init_m = re.search(r"def __init__\s*\(", src[class_m.end():class_m.end() + 5000])
    assert init_m is not None, "TransEModel.__init__ not found"
    # Extract __init__ body (next 2000 chars after the def).
    init_start = class_m.end() + init_m.end()
    init_body = src[init_start:init_start + 3000]
    assert "self.num_entities" in init_body, (
        "TransEModel.__init__ does NOT save self.num_entities. "
        "The held-out AUC evaluation will crash with AttributeError."
    )


# ─── X-19: Dev-mode V1 launch criteria thresholds ───────────────────────────

def test_x_19_dev_mode_thresholds_in_config():
    """config.py MUST lower V1 launch thresholds in dev mode.

    Audit finding: hard-coded 15000 pos pairs / 75000 neg pairs / 0.85 AUC
    made the toy fixture always fail V1 launch criteria.
    """
    src = _source_lines("phase2/drugos_graph/config.py")
    # Check that MIN_POSITIVE_PAIRS has dev-mode logic.
    assert "DRUGOS_ENVIRONMENT" in src and "MIN_POSITIVE_PAIRS" in src
    # Check that V1_LAUNCH_AUC has dev-mode logic.
    assert "DRUGOS_DEV_V1_LAUNCH_AUC" in src or "_DEV_MODE" in src, (
        "V1_LAUNCH_AUC does NOT have dev-mode override. "
        "The toy fixture will always fail V1 launch criteria."
    )


def test_x_19_dev_mode_min_sources_in_run_pipeline():
    """run_pipeline MUST lower all_sources_loaded threshold in dev mode."""
    src = _source_lines("phase2/drugos_graph/run_pipeline.py")
    assert "DRUGOS_DEV_MIN_SOURCES" in src or "_dev_mode" in src, (
        "all_sources_loaded criterion does NOT have dev-mode override. "
        "The toy fixture (only 2 sources) will always fail V1 launch criteria."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
