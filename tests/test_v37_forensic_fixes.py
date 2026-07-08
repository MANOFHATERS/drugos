#!/usr/bin/env python3
"""FORENSIC v37 master fix verification tests.

Verifies the additional per-file fixes applied on top of v36.

Run from the v37_master directory:
    cd /home/z/my-project/workspace/v37_master
    PYTHONPATH=phase1:phase2 python /home/z/my-project/scripts/test_v37_forensic_fixes.py
"""

import os
import sys
import re
from pathlib import Path

WORKSPACE = Path("/home/z/my-project/workspace/v37_master")
sys.path.insert(0, str(WORKSPACE))
sys.path.insert(0, str(WORKSPACE / "phase1"))
sys.path.insert(0, str(WORKSPACE / "phase2"))

PASS = 0
FAIL = 0
ERRORS = []


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        ERRORS.append(f"{name}: {detail}")
        print(f"  [FAIL] {name} — {detail}")


def section(title):
    print(f"\n{'='*70}\n{title}\n{'='*70}")


# ─────────────────────────────────────────────────────────────────────────────
# Issue 27: Edge MERGE ON CREATE/ON MATCH
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 27: Edge MERGE with ON CREATE SET / ON MATCH SET")

def test_issue27():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "kg_builder.py").read_text()
    check("Edge MERGE has ON CREATE SET",
          "ON CREATE SET r += row.props" in src,
          "ON CREATE SET not found for edges")
    check("Edge MERGE has ON MATCH SET",
          "ON MATCH SET r += row.props" in src,
          "ON MATCH SET not found for edges")
    check("Edge MERGE has _version coalesce",
          "coalesce(r._version, 0) + 1" in src,
          "_version coalesce not found for edges")

test_issue27()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 28: _deduplicate_batch only dead-letters content conflicts
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 28: _deduplicate_batch content-conflict-only dead-lettering")

def test_issue28():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "kg_builder.py").read_text()
    check("conflicts list tracking present",
          "conflicts: list[Any] = []" in src,
          "conflicts list not found")
    check("Content comparison logic present",
          "prev != curr" in src,
          "content comparison not found")
    check("Only conflicts dead-lettered (not all dups)",
          "for dup_id in conflicts:" in src,
          "conflicts-only dead-letter not found")
    check("Reason reflects content conflict",
          "duplicate_in_batch_content_conflict" in src,
          "reason string not updated")

test_issue28()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 7: OMIM MIM numbers prefixed with MIM:
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 7: OMIM MIM numbers namespaced with MIM: prefix")

def test_issue7():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "omim_loader.py").read_text()
    check("MIM: prefix applied to gene_mim fallbacks",
          'return f"MIM:{mim_id}"' in src,
          "MIM: prefix not applied")
    check("SYM: prefix preserved",
          "mim_id.startswith(\"SYM:\")" in src,
          "SYM: check not found")
    # Check ID_PATTERNS accepts MIM:
    kg_src = (WORKSPACE / "phase2" / "drugos_graph" / "kg_builder.py").read_text()
    check("ID_PATTERNS Gene accepts MIM:\\d+",
          "MIM:\\\\d+" in kg_src or "MIM:\\d+" in kg_src,
          "MIM: pattern not in ID_PATTERNS")

test_issue7()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 9: _ASSOC_TYPE_TO_REL moved to module level
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 9: DisGeNET assoc-type map at module level")

def test_issue9():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "disgenet_loader.py").read_text()
    check("Module-level _DISGENET_ASSOC_TYPE_TO_REL defined",
          "_DISGENET_ASSOC_TYPE_TO_REL: Dict[str, str]" in src,
          "module-level constant not found")
    check("Function references module-level constant",
          "_ASSOC_TYPE_TO_REL = _DISGENET_ASSOC_TYPE_TO_REL" in src,
          "function doesn't reference module constant")

test_issue9()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 10: INCHIKEY_REGEX comment corrected
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 10: INCHIKEY_REGEX comment (14-10-1 layout)")

def test_issue10():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "config.py").read_text()
    check("Comment describes 14-10-1 layout",
          "14 uppercase letters" in src and "10 uppercase letters" in src,
          "14-10-1 layout not in comment")
    check("Old wrong 14-8-1-1-1 comment removed",
          "8 chars" not in src or "14 chars + hyphen +\n# 8 chars" not in src,
          "old wrong comment still present")

test_issue10()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 13: is_dev_mode() lazy function
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 13: is_dev_mode() lazy evaluation")

def test_issue13():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "config.py").read_text()
    check("is_dev_mode() function defined",
          "def is_dev_mode() -> bool:" in src,
          "is_dev_mode function not defined")
    check("Function reads DRUGOS_ENVIRONMENT lazily",
          'os.environ.get("DRUGOS_ENVIRONMENT", "dev")' in src,
          "lazy env read not in function")

test_issue13()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 20: TransE score sign comment corrected
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 20: TransE score sign comment matches code")

def test_issue20():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "transe_model.py").read_text()
    check("Comment says POSITIVE L1 distance",
          "POSITIVE L1 distance" in src,
          "positive distance comment not found")
    check("Old wrong negative-sign comment removed from main block",
          "score(h,r,t) = -||h + r - t||\n                #     LOWER" not in src,
          "old wrong comment still present")

test_issue20()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 21: TransE model.config default in __init__
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 21: TransE model.config default in __init__")

def test_issue21():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "transe_model.py").read_text()
    check("_DefaultTransEConfig class defined",
          "class _DefaultTransEConfig:" in src,
          "_DefaultTransEConfig class not found")
    check("model.config set in __init__",
          "self.config: Any = _DefaultTransEConfig()" in src,
          "config not set in __init__")
    check("Default uses strict_bordes",
          'relation_norm_mode: str = "strict_bordes"' in src,
          "default mode not strict_bordes")

test_issue21()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 22: pos_expanded shape assertion
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 22: pos_expanded shape assertion")

def test_issue22():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "transe_model.py").read_text()
    check("Shape assertion present",
          "assert pos_expanded.shape == neg_scores.shape" in src,
          "shape assertion not found")
    check("Assertion has descriptive message",
          "Shape mismatch" in src and "issue 22" in src,
          "descriptive message not found")

test_issue22()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 3: gpu_utils batch_size formula includes Adam memory
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 3: gpu_utils batch_size formula (Adam memory factor)")

def test_issue3():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "gpu_utils.py").read_text()
    check("_ADAM_MEMORY_FACTOR defined",
          "_ADAM_MEMORY_FACTOR = 4" in src,
          "Adam memory factor not found")
    check("Formula includes Adam factor",
          "* _ADAM_MEMORY_FACTOR" in src,
          "formula doesn't use Adam factor")

test_issue3()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 4: mlflow_tracker start_run exception-safe
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 4: mlflow_tracker start_run exception-safe")

def test_issue4():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "mlflow_tracker.py").read_text()
    check("start_run has try/except",
          "except Exception as e:" in src and "MLflow start_run failed" in src,
          "try/except not found in start_run")
    check("self.run set to None on failure",
          "self.run = None" in src,
          "run not reset to None on failure")

test_issue4()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 37: pyg_builder uses torch.flip for edge reversal
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 37: pyg_builder torch.flip for edge reversal")

def test_issue37():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "pyg_builder.py").read_text()
    check("Uses torch.flip for edge reversal",
          "torch.flip(edge_index, [0])" in src,
          "torch.flip not used")
    check("Old torch.stack([edge_index[1], edge_index[0]]) removed",
          "torch.stack(\n                                [edge_index[1], edge_index[0]]\n                            )" not in src,
          "old torch.stack still present")

test_issue37()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 38: pyg_builder vectorized edge dedup
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 38: pyg_builder vectorized edge dedup")

def test_issue38():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "pyg_builder.py").read_text()
    check("Uses torch.unique for dedup",
          "torch.unique" in src,
          "torch.unique not used")
    check("Uses scatter_reduce_ for first occurrence",
          "scatter_reduce_" in src,
          "scatter_reduce_ not used")
    check("Old Python set + for loop removed",
          "_edges_set: set = set()" not in src,
          "old Python set dedup still present")

test_issue38()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 39: pyg_builder node feature shape validation
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 39: pyg_builder node feature shape validation")

def test_issue39():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "pyg_builder.py").read_text()
    check("Node feature shape check present",
          "feat_rows != num_nodes" in src,
          "feature shape check not found")
    check("Raises ValueError on mismatch",
          "feature tensor has" in src and "issue 39" in src,
          "ValueError not raised on mismatch")

test_issue39()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 18: graph_transformer forward() bare-embedding fallback
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 18: graph_transformer forward() zeros fallback (no raise)")

def test_issue18():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "graph_transformer_model.py").read_text()
    check("Bare-embedding fallback has try/except ValueError",
          'except ValueError:' in src and 'bare-embedding fallback returning' in src,
          "try/except fallback not found")
    check("Returns zeros instead of raising",
          "torch.zeros(" in src and "issue 18 root fix" in src,
          "zeros fallback not found")

test_issue18()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 35: step11 surfaces dropped pairs count
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 35: step11 surfaces dropped temporal-split pairs")

def test_issue35():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "run_pipeline.py").read_text()
    check("_dropped_count computed from _ts_result",
          '_dropped_count = len(_ts_result.get("dropped", []))' in src,
          "dropped count not computed")
    check("Warning logged when dropped > 0",
          "temporal split DROPPED" in src,
          "warning not logged")
    check("dropped count in info log",
          "dropped=%d" in src,
          "dropped count not in info log")

test_issue35()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 51: checkpoint JSON preserves native types
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 51: _serialize_for_json preserves native types")

def test_issue51():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "run_pipeline.py").read_text()
    check("Preserves bool/int/float/str/None",
          "if obj is None or isinstance(obj, (bool, int, float, str)):" in src,
          "native type preservation not found")
    check("np.bool_ handled",
          "isinstance(obj, (np.bool_,))" in src,
          "np.bool_ not handled")
    check("Dict keys stringified",
          "str(k): _serialize_for_json(v)" in src,
          "dict keys not stringified")

test_issue51()


# ─────────────────────────────────────────────────────────────────────────────
# Issues 49-50: pyproject.toml deps + numpy conflict
# ─────────────────────────────────────────────────────────────────────────────
section("Issues 49-50: pyproject.toml missing deps + numpy conflict")

def test_issues49_50():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "pyproject.toml").read_text()
    check("psutil declared as direct dep",
          '"psutil>=5.9"' in src,
          "psutil not declared")
    check("certifi declared as direct dep",
          '"certifi>=2024.2"' in src,
          "certifi not declared")
    check("backports.tarfile declared",
          "backports.tarfile" in src,
          "backports.tarfile not declared")
    check("[geo] numpy pin aligned with main (<3.0)",
          '"numpy>=1.24,<3.0"' in src,
          "[geo] numpy pin not aligned")

test_issues49_50()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 10 (base_pipeline): backoff formula aligned with _http_client
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 10: base_pipeline backoff formula aligned")

def test_issue10_bp():
    src = (WORKSPACE / "phase1" / "pipelines" / "base_pipeline.py").read_text()
    check("Uses 2 ** attempt (not 2 ** (attempt-1))",
          "1.0 * (2 ** attempt) + random.uniform(0, 1)" in src,
          "backoff formula not aligned")
    check("Old formula removed",
          "(2 ** (attempt - 1)) + random.uniform(0, 1)" not in src,
          "old formula still present")

test_issue10_bp()


# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
section("SUMMARY")
print(f"  PASS: {PASS}")
print(f"  FAIL: {FAIL}")
if ERRORS:
    print(f"\n  FAILURES:")
    for e in ERRORS:
        print(f"    - {e}")
print(f"\n  Result: {'ALL CHECKS PASSED' if FAIL == 0 else f'{FAIL} CHECKS FAILED'}")
sys.exit(0 if FAIL == 0 else 1)
