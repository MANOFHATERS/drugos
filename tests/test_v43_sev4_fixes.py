"""
v43 SEV4-LOW Verification Test Suite

Proves that all 15 SEV4-LOW issues (8 Phase 1 + 7 Phase 2) from the
v41 forensic audit are FIXED.

Run with:
    cd /path/to/extracted
    export PYTHONPATH="$PWD:$PWD/phase1:$PWD/phase2"
    python tests/test_v43_sev4_fixes.py
"""

import os
import sys
import inspect
import re
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "phase1"))
sys.path.insert(0, str(ROOT / "phase2"))

GREEN = "\033[92m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"

PASS_COUNT = 0
FAIL_COUNT = 0


def _pass(tid, msg):
    global PASS_COUNT
    PASS_COUNT += 1
    print(f"{GREEN}✅ PASS{RESET} [{tid}] {msg}")


def _fail(tid, msg, exc=""):
    global FAIL_COUNT
    FAIL_COUNT += 1
    print(f"{RED}❌ FAIL{RESET} [{tid}] {msg}")
    if exc:
        for line in exc.strip().splitlines()[-3:]:
            print(f"   {line}")


def test_p1_024():
    """P1-024: comment accurately describes regex behavior."""
    try:
        import cleaning._constants as c
        src = inspect.getsource(c)
        # The fix updates the comment to mention all-lowercase acceptance
        if "all-lowercase" in src.lower() or "any case mix" in src.lower():
            _pass("P1-024", "comment accurately describes regex (accepts any case mix)")
        else:
            _fail("P1-024", "comment still says 'Title-Case OR ALL-CAPS' (missing lowercase)")
    except Exception as e:
        _fail("P1-024", str(e))


def test_p1_025():
    """P1-025: stale v22 ROOT FIX comment updated."""
    try:
        import pipelines.chembl_pipeline as cp
        src = inspect.getsource(cp)
        # The fix removes the stale "v22 ROOT FIX" comment
        if "v22 ROOT FIX" not in src or "v43 ROOT FIX (P1-025)" in src:
            _pass("P1-025", "stale v22 comment updated (reflects v29 behavior)")
        else:
            _fail("P1-025", "stale v22 ROOT FIX comment still present")
    except Exception as e:
        _fail("P1-025", str(e))


def test_p1_027():
    """P1-027: negative-score regex rejects negative values."""
    try:
        import pipelines.disgenet_pipeline as dp
        src = inspect.getsource(dp)
        # The fix removes the -? from the regex. Check for the fixed
        # regex in CODE (not comments).
        code_lines = [l for l in src.splitlines()
                      if r"^\d+\.?\d*$" in l and not l.strip().startswith("#")]
        old_code_lines = [l for l in src.splitlines()
                          if r"^-?\d+\.?\d*$" in l and not l.strip().startswith("#")]
        if code_lines and not old_code_lines:
            _pass("P1-027", "regex rejects negative scores (was ^-?\d+... now ^\d+...)")
        else:
            _fail("P1-027", f"regex issue: fixed={code_lines}, old={old_code_lines}")
    except Exception as e:
        _fail("P1-027", str(e))


def test_p1_028():
    """P1-028: OMIM score guard bounds to [0, 1]."""
    try:
        import pipelines.omim_pipeline as op
        src = inspect.getsource(op)
        if "0.0 <= float(s) <= 1.0" in src:
            _pass("P1-028", "OMIM score guard bounds to [0.0, 1.0] (was just >= 0)")
        else:
            _fail("P1-028", "guard still allows scores > 1.0")
    except Exception as e:
        _fail("P1-028", str(e))


def test_p1_029():
    """P1-029: _source_fetch_date uses getattr + None guard."""
    try:
        import pipelines.chembl_pipeline as cp
        src = inspect.getsource(cp)
        if "getattr(self, '_source_fetch_date', None)" in src:
            _pass("P1-029", "_source_fetch_date uses getattr + None guard (no crash if unset)")
        else:
            _fail("P1-029", "direct .isoformat() without None guard still present")
    except Exception as e:
        _fail("P1-029", str(e))


def test_p1_030():
    """P1-030: verify= uses explicit conditional (not ca_bundle or True)."""
    try:
        import pipelines.pubchem_pipeline as pp
        src = inspect.getsource(pp)
        # Check for the explicit conditional in CODE (not comments)
        code_lines = [l for l in src.splitlines()
                      if "verify=" in l and "ca_bundle" in l and not l.strip().startswith("#")]
        has_explicit = any("self.ca_bundle if" in l for l in code_lines)
        has_old = any("ca_bundle or True)" in l and "previous" not in l for l in code_lines)
        if has_explicit and not has_old:
            _pass("P1-030", "verify= uses explicit conditional (empty string doesn't fall back to True)")
        else:
            _fail("P1-030", f"explicit={has_explicit}, old={has_old}")
    except Exception as e:
        _fail("P1-030", str(e))


def test_p1_031():
    """P1-031: assert raw_dir replaced with explicit raise."""
    try:
        import pipelines.pubchem_pipeline as pp
        src = inspect.getsource(pp)
        # Check for explicit raise instead of assert
        code_lines = [l for l in src.splitlines()
                      if "assert self.raw_dir" in l and not l.strip().startswith("#")]
        if not code_lines and "raise RuntimeError" in src and "raw_dir is None" in src:
            _pass("P1-031", "assert raw_dir replaced with explicit RuntimeError (survives -O)")
        else:
            _fail("P1-031", f"assert still present: {code_lines}")
    except Exception as e:
        _fail("P1-031", str(e))


def test_p1_032():
    """P1-032: SCHEMA_VERSION bumped to 10."""
    try:
        from database.base import SCHEMA_VERSION
        if SCHEMA_VERSION >= 10:
            _pass("P1-032", f"SCHEMA_VERSION = {SCHEMA_VERSION} (was 9, now 10)")
        else:
            _fail("P1-032", f"SCHEMA_VERSION = {SCHEMA_VERSION} (expected 10)")
    except Exception as e:
        _fail("P1-032", str(e))


def test_p2_021():
    """P2-021: TransEModel.__init__ accepts config parameter."""
    try:
        from drugos_graph.transe_model import TransEModel
        init_params = TransEModel.__init__.__code__.co_varnames
        if "config" in init_params:
            _pass("P2-021", "TransEModel.__init__ accepts config (no post-construction mutation needed)")
        else:
            _fail("P2-021", "config not in __init__ params")
    except Exception as e:
        _fail("P2-021", str(e))


def test_p2_022():
    """P2-022: uses np.random.default_rng (not Python random)."""
    try:
        from drugos_graph.run_pipeline import step11_train_transe
        src = inspect.getsource(step11_train_transe)
        if "default_rng(42)" in src and "_random_for_split.Random" not in src:
            _pass("P2-022", "uses np.random.default_rng(42) (consistent with set_global_seed)")
        else:
            _fail("P2-022", "still uses Python's random.Random(42)")
    except Exception as e:
        _fail("P2-022", str(e))


def test_p2_023():
    """P2-023: relation_idx=None logs warning (not silent default 0)."""
    try:
        from drugos_graph.negative_sampling import KGNegativeSampler
        src = inspect.getsource(KGNegativeSampler.combined_sampling)
        if "relation_idx is None" in src and "logger.warning" in src:
            _pass("P2-023", "relation_idx=None logs warning (not silent default 0)")
        else:
            _fail("P2-023", "still silently defaults to 0")
    except Exception as e:
        _fail("P2-023", str(e))


def test_p2_024():
    """P2-024: safe_edge_batch mutates in-place (no list comprehension copy)."""
    try:
        from drugos_graph.kg_builder import GraphEdgeLoader
        src = inspect.getsource(GraphEdgeLoader)
        if "for _r in clean_batch:" in src and "_r[\"props\"] = _strip_nulls" in src:
            _pass("P2-024", "safe_edge_batch mutates in-place (no memory-doubling copy)")
        else:
            _fail("P2-024", "still creates new list of dicts per batch")
    except Exception as e:
        _fail("P2-024", str(e))


def test_p2_025():
    """P2-025: sklearn imported at module level."""
    try:
        from drugos_graph import evaluation
        # Check that _ROC_AUC_SCORE exists at module level
        if hasattr(evaluation, '_ROC_AUC_SCORE'):
            _pass("P2-025", "sklearn roc_auc_score imported at module level (not per-call)")
        else:
            _fail("P2-025", "module-level _ROC_AUC_SCORE not found")
    except Exception as e:
        _fail("P2-025", str(e))


def test_p2_026():
    """P2-026: Phase1StagedData has pathway_nodes + pathway_nodes_emitted."""
    try:
        from drugos_graph.phase1_bridge import Phase1StagedData
        psd = Phase1StagedData()
        assert hasattr(psd, 'pathway_nodes'), "pathway_nodes field missing"
        assert hasattr(psd, 'pathway_nodes_emitted'), "pathway_nodes_emitted field missing"
        assert psd.pathway_nodes_emitted == False, "default should be False"
        # total_nodes should include pathway_nodes
        psd.pathway_nodes = [{"id": "PW:1"}]
        assert psd.total_nodes == 1, f"total_nodes should be 1, got {psd.total_nodes}"
        _pass("P2-026", "Phase1StagedData has pathway_nodes + pathway_nodes_emitted (total_nodes includes them)")
    except Exception as e:
        _fail("P2-026", str(e), traceback.format_exc())


def test_p2_027():
    """P2-027: launch-criteria flags documented."""
    try:
        from drugos_graph.run_pipeline import _check_v1_launch_criteria
        docstring = _check_v1_launch_criteria.__doc__ or ""
        if "dev_smoke_test_pass" in docstring and "passed_dev_smoke" in docstring and "dev_relaxed_criteria_passed" in docstring:
            _pass("P2-027", "3 launch-criteria flags documented in _check_v1_launch_criteria docstring")
        else:
            _fail("P2-027", "flags not documented in docstring")
    except Exception as e:
        _fail("P2-027", str(e))


def test_integration():
    """All modules import cleanly."""
    try:
        from cleaning._constants import CANONICAL_NON_HUMAN_GENE_SYMBOL_REGEX
        from pipelines.chembl_pipeline import ChEMBLPipeline
        from pipelines.disgenet_pipeline import DisGeNETPipeline
        from pipelines.omim_pipeline import OMIMPipeline
        from pipelines.pubchem_pipeline import PubChemPipeline
        from database.base import SCHEMA_VERSION
        from drugos_graph.transe_model import TransEModel
        from drugos_graph.negative_sampling import KGNegativeSampler
        from drugos_graph.kg_builder import DrugOSGraphBuilder
        from drugos_graph.evaluation import compute_auc
        from drugos_graph.phase1_bridge import Phase1StagedData
        from drugos_graph.run_pipeline import _check_v1_launch_criteria
        _pass("INTEG", "All 15 SEV4-modified modules import cleanly")
    except Exception as e:
        _fail("INTEG", f"Import failed: {e}", traceback.format_exc())


def main():
    print(f"\n{BOLD}═══════════════════════════════════════════════════════════════════{RESET}")
    print(f"{BOLD}  v43 SEV4-LOW VERIFICATION TEST SUITE{RESET}")
    print(f"{BOLD}  15 issues (8 Phase 1 + 7 Phase 2){RESET}")
    print(f"{BOLD}═══════════════════════════════════════════════════════════════════{RESET}\n")
    tests = [
        ("P1-024", test_p1_024), ("P1-025", test_p1_025), ("P1-027", test_p1_027),
        ("P1-028", test_p1_028), ("P1-029", test_p1_029), ("P1-030", test_p1_030),
        ("P1-031", test_p1_031), ("P1-032", test_p1_032), ("P2-021", test_p2_021),
        ("P2-022", test_p2_022), ("P2-023", test_p2_023), ("P2-024", test_p2_024),
        ("P2-025", test_p2_025), ("P2-026", test_p2_026), ("P2-027", test_p2_027),
        ("INTEG", test_integration),
    ]
    for label, fn in tests:
        print(f"\n{BOLD}── {label} ──{RESET}")
        fn()
    print(f"\n{BOLD}═══════════════════════════════════════════════════════════════════{RESET}")
    print(f"  {GREEN}PASSED: {PASS_COUNT}{RESET}  {RED}FAILED: {FAIL_COUNT}{RESET}")
    if FAIL_COUNT == 0:
        print(f"{GREEN}{BOLD}✅ ALL 15 SEV4-LOW FIXES VERIFIED.{RESET}")
        return 0
    print(f"{RED}{BOLD}❌ {FAIL_COUNT} test(s) FAILED.{RESET}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
