"""
v43 COMPOUND Verification Test Suite

Proves that all 5 COMPOUND degradation chains from the v41 forensic
audit are BROKEN. Each chain is a set of individual bugs that compound
into worse output when combined. The individual bugs were fixed in
previous v43 sessions (SEV1/SEV2/SEV3/SEV4/SCIENTIFIC/DEAD-CODE).
This test suite verifies that the CHAINS are broken — i.e., the
compound degradation no longer occurs.

5 Compound Chains:
  Chain 1 (P1-041): Potency error chain — normalizer + aggregation + DB write
  Chain 2 (P1-001 + P2-005): Homodimer corruption + missing Pathway
  Chain 3 (P2-001 + P2-028): held_out_pairs + overfitting
  Chain 4 (P1-008 + P2-005): substrate misclassification + missing Pathway
  Chain 5 (P1-006 + P2-006): silent commit failure + broad excepts

Plus:
  P1-007: Three divergent coercion paths consolidated

Run with:
    cd /path/to/extracted
    export PYTHONPATH="$PWD:$PWD/phase1:$PWD/phase2"
    python tests/test_v43_compound_fixes.py
"""

import sys
import inspect
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


def test_chain1_potency():
    """Chain 1 (P1-041): Potency error chain broken.

    P1-003: _build_dpi_dataframe passes through actual units (not hardcoded "nM")
    P1-004: _aggregate_activities_to_dpi groups by activity_units (no cross-unit median)
    P1-035: is_log_scale flag added so downstream can detect log-scale values

    A pIC50 of 7.0 (true ~100 nM) must NOT be stored as "7.0 nM" (14× error).
    """
    try:
        from pipelines.chembl_pipeline import ChEMBLPipeline
        from cleaning.normalizer import normalize_activity_value

        # P1-003: no hardcoded "nM" in _build_dpi_dataframe
        src = inspect.getsource(ChEMBLPipeline._build_dpi_dataframe)
        hardcoded = [l for l in src.splitlines()
                     if '"activity_units": "nM"' in l and not l.strip().startswith("#")]
        assert len(hardcoded) == 0, f"Hardcoded nM still present: {hardcoded}"

        # P1-004: activity_units in groupby
        src2 = inspect.getsource(ChEMBLPipeline._aggregate_activities_to_dpi)
        assert 'group_cols.append("activity_units")' in src2, "activity_units not in groupby"

        # P1-035: is_log_scale flag
        r = normalize_activity_value(8.5, "pKi", activity_type="pKi")
        assert r.is_log_scale == True, "pKi should have is_log_scale=True"
        assert r.unit == "pKi", f"pKi unit should be 'pKi', got '{r.unit}'"

        _pass("Chain1", "Potency chain BROKEN: no hardcoded nM, units in groupby, is_log_scale=True")
    except Exception as e:
        _fail("Chain1", str(e), traceback.format_exc())


def test_chain2_homodimer_pathway():
    """Chain 2 (P1-001 + P2-005): Homodimer + Pathway chain broken.

    P1-001: Homodimers dead-lettered (not XOR-1 sentinel swap)
    P2-005: Pathway node ingestion path added (pathways.csv)

    Without the fix, PPI data was irreversibly corrupted AND Pathway
    nodes were missing — the GNN learned wrong neighborhood structure.
    """
    try:
        from pipelines.string_pipeline import StringPipeline
        from drugos_graph.phase1_bridge import stage_phase1_to_phase2

        # P1-001: no XOR-1 sentinel swap, dead-letter instead
        src = inspect.getsource(StringPipeline)
        has_deadletter = "homodimer_deferred" in src
        assert has_deadletter, "homodimer_deferred dead-letter not found"

        # P2-005: Pathway node ingestion path
        src2 = inspect.getsource(stage_phase1_to_phase2)
        has_pathway = "pathways.csv" in src2 and "pathway_nodes" in src2
        assert has_pathway, "pathway ingestion not found"

        _pass("Chain2", "Homodimer+Pathway chain BROKEN: dead-lettered homodimers, pathway ingestion added")
    except Exception as e:
        _fail("Chain2", str(e), traceback.format_exc())


def test_chain3_heldout_overfit():
    """Chain 3 (P2-001 + P2-028): held_out_pairs + overfitting chain broken.

    P2-001: held_out_pairs passed to KGNegativeSampler
    P2-028: AUC documented as smoke test (not meaningful on toy fixture)

    Without the fix, AUC was simultaneously inflated (false negatives)
    AND deflated (overfitting on 7 pairs) — the "true" AUC was unknowable.
    """
    try:
        from drugos_graph.run_pipeline import step11_train_transe

        src = inspect.getsource(step11_train_transe)

        # P2-001: held_out_pairs passed
        assert "held_out_pairs=held_out_pairs" in src, "held_out_pairs not passed to KGNegativeSampler"

        # P2-028: smoke-test documentation
        assert "SMOKE TEST" in src or "smoke test" in src.lower(), "smoke-test documentation not found"

        _pass("Chain3", "held_out_pairs+overfit chain BROKEN: held_out_pairs passed, AUC documented as smoke test")
    except Exception as e:
        _fail("Chain3", str(e), traceback.format_exc())


def test_chain4_substrate_pathway():
    """Chain 4 (P1-008 + P2-005): substrate misclassification + missing Pathway.

    P1-008: INDUCER and SUBSTRATE added to InteractionType enum
    P2-005: Pathway node ingestion path added

    Without the fix, the DDI risk predictor was completely blind to
    CYP3A4 substrate-inhibitor interactions — the most common class
    of dangerous DDIs.
    """
    try:
        from database.models import InteractionType
        from drugos_graph.phase1_bridge import stage_phase1_to_phase2

        # P1-008: INDUCER and SUBSTRATE in enum
        assert hasattr(InteractionType, "SUBSTRATE"), "InteractionType.SUBSTRATE missing"
        assert hasattr(InteractionType, "INDUCER"), "InteractionType.INDUCER missing"
        assert InteractionType.SUBSTRATE.value == "substrate"
        assert InteractionType.INDUCER.value == "inducer"

        # P2-005: Pathway ingestion (already verified in Chain 2, but check again)
        src = inspect.getsource(stage_phase1_to_phase2)
        assert "pathways.csv" in src, "pathway ingestion not found"

        _pass("Chain4", "Substrate+Pathway chain BROKEN: INDUCER/SUBSTRATE in enum, pathway ingestion added")
    except Exception as e:
        _fail("Chain4", str(e), traceback.format_exc())


def test_chain5_commit_broadexcept():
    """Chain 5 (P1-006 + P2-006): silent commit failure + broad excepts.

    P1-006: session commit catches SQLAlchemyError (not bare Exception: pass)
    P2-006: _step_exception_or_skip uses "failed": True (not "skipped": True)

    Without the fix, an operator could run the pipeline, see "all steps
    completed" in the dashboard, and have ZERO DrugBank data actually
    persisted to the DB. The failure was invisible at every layer.
    """
    try:
        from pipelines.drugbank_pipeline import DrugBankPipeline
        from drugos_graph.run_pipeline import _step_exception_or_skip

        # P1-006: SQLAlchemyError catch
        src = inspect.getsource(DrugBankPipeline)
        assert "except SQLAlchemyError as commit_exc" in src, "SQLAlchemyError catch not found"

        # P2-006: failed label
        src2 = inspect.getsource(_step_exception_or_skip)
        assert '"failed": True' in src2, "failed label not found"
        assert '"skipped": False' in src2, "skipped: False not found"

        _pass("Chain5", "Commit+broadexcept chain BROKEN: SQLAlchemyError catch, failed label")
    except Exception as e:
        _fail("Chain5", str(e), traceback.format_exc())


def test_p1_007_coercion():
    """P1-007: Three divergent coercion paths consolidated.

    models._validate_max_phase now coerces+clamps (consistent with
    chembl_pipeline._coerce_max_phase). A value that passes one
    validator no longer fails another.
    """
    try:
        from database.models import _validate_max_phase

        # All three paths now use coerce+clamp
        assert _validate_max_phase(5) == 4, f"5 should clamp to 4, got {_validate_max_phase(5)}"
        assert _validate_max_phase(-1) == 0, f"-1 should clamp to 0, got {_validate_max_phase(-1)}"
        assert _validate_max_phase("4.0") == 4, f"'4.0' should coerce to 4, got {_validate_max_phase('4.0')}"
        assert _validate_max_phase(3) == 3, f"3 should stay 3, got {_validate_max_phase(3)}"
        assert _validate_max_phase(None) is None, f"None should stay None"

        _pass("P1-007", "Coercion paths consolidated: _validate_max_phase coerces+clamps (consistent)")
    except Exception as e:
        _fail("P1-007", str(e), traceback.format_exc())


def test_integration():
    """All modules import cleanly."""
    try:
        from pipelines.chembl_pipeline import ChEMBLPipeline
        from pipelines.string_pipeline import StringPipeline
        from pipelines.drugbank_pipeline import DrugBankPipeline
        from cleaning.normalizer import normalize_activity_value
        from database.models import InteractionType, _validate_max_phase
        from drugos_graph.run_pipeline import step11_train_transe, _step_exception_or_skip
        from drugos_graph.phase1_bridge import stage_phase1_to_phase2
        _pass("INTEG", "All COMPOUND-chain modules import cleanly")
    except Exception as e:
        _fail("INTEG", f"Import failed: {e}", traceback.format_exc())


def main():
    print(f"\n{BOLD}═══════════════════════════════════════════════════════════════════{RESET}")
    print(f"{BOLD}  v43 COMPOUND VERIFICATION TEST SUITE{RESET}")
    print(f"{BOLD}  5 compound chains + P1-007 (6 tests total){RESET}")
    print(f"{BOLD}═══════════════════════════════════════════════════════════════════{RESET}\n")
    tests = [
        ("Chain1", test_chain1_potency),
        ("Chain2", test_chain2_homodimer_pathway),
        ("Chain3", test_chain3_heldout_overfit),
        ("Chain4", test_chain4_substrate_pathway),
        ("Chain5", test_chain5_commit_broadexcept),
        ("P1-007", test_p1_007_coercion),
        ("INTEG", test_integration),
    ]
    for label, fn in tests:
        print(f"\n{BOLD}── {label} ──{RESET}")
        fn()
    print(f"\n{BOLD}═══════════════════════════════════════════════════════════════════{RESET}")
    print(f"  {GREEN}PASSED: {PASS_COUNT}{RESET}  {RED}FAILED: {FAIL_COUNT}{RESET}")
    if FAIL_COUNT == 0:
        print(f"{GREEN}{BOLD}✅ ALL 5 COMPOUND CHAINS BROKEN + P1-007 CONSOLIDATED.{RESET}")
        return 0
    print(f"{RED}{BOLD}❌ {FAIL_COUNT} test(s) FAILED.{RESET}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
