#!/usr/bin/env python3
"""FORENSIC v38 master fix verification tests.

Verifies the additional per-file fixes applied on top of v37.

Run from the v38_master directory:
    cd /home/z/my-project/workspace/v38_master
    PYTHONPATH=phase1:phase2 python /home/z/my-project/scripts/test_v38_forensic_fixes.py
"""

import os
import sys
import json
from pathlib import Path

WORKSPACE = Path("/home/z/my-project/workspace/v38_master")
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
# Issue 5: chembl_activities standard_relation dead contract
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 5: chembl_activities standard_relation schema contract")

def test_issue5():
    with open(WORKSPACE / "phase1" / "pipelines" / "schema" / "v1.json") as f:
        schema = json.load(f)
    props = schema.get("properties", {})
    sr = props.get("chembl_activities_clean.csv", {}).get("properties", {}).get("standard_relation", {})
    desc = sr.get("description", "")
    check("standard_relation description documents default filter",
          "defaults to {'='} only" in desc or "defaults to" in desc.lower(),
          f"description doesn't document default filter: {desc[:80]}")

test_issue5()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 6: drugbank_drugs.csv schema has all 35 columns
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 6: drugbank_drugs.csv schema has all 35 columns")

def test_issue6():
    with open(WORKSPACE / "phase1" / "pipelines" / "schema" / "v1.json") as f:
        schema = json.load(f)
    props = schema.get("properties", {})
    db_props = props.get("drugbank_drugs.csv", {}).get("properties", {})
    # Check critical missing columns are now present
    check("is_withdrawn column in schema",
          "is_withdrawn" in db_props,
          "is_withdrawn missing")
    check("clinical_status column in schema",
          "clinical_status" in db_props,
          "clinical_status missing")
    check("groups column in schema",
          "groups" in db_props,
          "groups missing")
    check("mechanism_of_action column in schema",
          "mechanism_of_action" in db_props,
          "mechanism_of_action missing")
    check("smiles column in schema",
          "smiles" in db_props,
          "smiles missing")
    check("max_phase column in schema",
          "max_phase" in db_props,
          "max_phase missing")
    check("chembl_id column in schema",
          "chembl_id" in db_props,
          "chembl_id missing")
    check("pubchem_cid column in schema",
          "pubchem_cid" in db_props,
          "pubchem_cid missing")
    # Count: should be at least 30 (we had 6 before, now 35)
    check("Schema has >= 30 columns",
          len(db_props) >= 30,
          f"only {len(db_props)} columns")

test_issue6()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 11: TARGET_TRANSE_AUC reads same env var as TransEConfig.target_auc
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 11: TARGET_TRANSE_AUC env var alignment")

def test_issue11():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "config.py").read_text()
    check("TARGET_TRANSE_AUC reads DRUGOS_TRANSE_TARGET_AUC",
          'os.environ.get("DRUGOS_TRANSE_TARGET_AUC"' in src and "TARGET_TRANSE_AUC" in src,
          "TARGET_TRANSE_AUC doesn't read the env var")

test_issue11()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 12: Side Effect / MedDRA_Term normalization helpers
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 12: adverse-event label normalization helpers")

def test_issue12():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "config.py").read_text()
    check("normalize_adverse_event_label function defined",
          "def normalize_adverse_event_label" in src,
          "function not defined")
    check("get_adverse_event_labels_for_cypher function defined",
          "def get_adverse_event_labels_for_cypher" in src,
          "function not defined")
    check("Cypher helper backtick-quotes 'Side Effect'",
          "`Side Effect`" in src,
          "backtick quoting not found")

test_issue12()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 43: HGT AUC only considered when not skipped
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 43: HGT AUC gated on not-skipped")

def test_issue43():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "run_pipeline.py").read_text()
    check("hgt_skipped flag computed",
          "hgt_skipped = r11b.get" in src,
          "hgt_skipped flag not computed")
    check("HGT AUC gated on not hgt_skipped",
          "if not hgt_skipped and hgt_val_auc" in src,
          "HGT AUC not gated on not-skipped")
    check("hgt_skipped in criteria",
          'criteria["hgt_skipped"]' in src,
          "hgt_skipped not in criteria")

test_issue43()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 36: _validate_drkg_df column-name aliasing
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 36: _validate_drkg_df column-name aliasing")

def test_issue36():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "training_data.py").read_text()
    check("_COLUMN_ALIASES dict defined",
          "_COLUMN_ALIASES" in src,
          "alias dict not found")
    check("head_id aliases include 'head'",
          '"head_id": ["head"' in src,
          "head_id alias not found")
    check("tail_id aliases include 'tail'",
          '"tail_id": ["tail"' in src,
          "tail_id alias not found")
    check("rename inplace for alias resolution",
          "drkg_df.rename(columns={alias: canonical}, inplace=True)" in src,
          "rename inplace not found")

test_issue36()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 46: UniProt accession TrEMBL comment corrected
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 46: UniProt TrEMBL comment corrected")

def test_issue46():
    src = (WORKSPACE / "phase2" / "drugos_graph" / "id_crosswalk.py").read_text()
    check("Comment says 'used by BOTH Swiss-Prot and TrEMBL'",
          "used by BOTH Swiss-Prot and TrEMBL" in src,
          "correct comment not found")
    check("Old misleading 'TrEMBL (unreviewed)' removed",
          "TrEMBL   (unreviewed):" not in src,
          "old misleading comment still present")

test_issue46()


# ─────────────────────────────────────────────────────────────────────────────
# Issue 15: chembl_pipeline teardown log says "finalised" not "initialised"
# ─────────────────────────────────────────────────────────────────────────────
section("Issue 15: chembl_pipeline teardown log says 'finalised'")

def test_issue15():
    src = (WORKSPACE / "phase1" / "pipelines" / "chembl_pipeline.py").read_text()
    check("Teardown logs 'finalised'",
          "ChEMBLPipeline finalised" in src,
          "teardown doesn't log 'finalised'")
    # Check that no logger.info call in the teardown method logs 'initialised'.
    # The word 'initialised' may appear in comments explaining the fix,
    # but the actual logger.info call should say 'finalised'.
    # Find the teardown method and extract its logger.info call.
    teardown_start = src.find("def teardown(self)")
    if teardown_start >= 0:
        # Get the next 1500 chars (teardown is ~30 lines)
        teardown_section = src[teardown_start:teardown_start + 1500]
        # Find the logger.info call within teardown
        log_idx = teardown_section.find("logger.info(")
        if log_idx >= 0:
            log_call = teardown_section[log_idx:log_idx + 200]
            check("Teardown logger.info logs 'finalised'",
                  "finalised" in log_call,
                  f"logger.info doesn't log 'finalised': {log_call[:80]}")
        else:
            check("Teardown has logger.info call", False, "no logger.info in teardown")
    else:
        check("Teardown method found", False, "teardown method not found")

test_issue15()


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
