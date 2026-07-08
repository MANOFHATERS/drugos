# V42 SEV1-CRITICAL VERIFICATION REPORT

**Date:** 2026-07-07
**Codebase:** v41_master_fixed.zip → v42_sev1_verified
**Scope:** Phase 1 (Data Ingestion) + Phase 2 (Knowledge Graph)
**Auditor:** Super Z (independent verification)

## Executive Summary

The v40 forensic audit report identified **7 SEV1-CRITICAL bugs**. The v41 ROOT FIX pass addressed ALL 7. This v42 report independently verifies — by reading the actual source code AND running runtime tests — that **ALL 7 SEV1-CRITICAL fixes are working correctly**.

| SEV1 # | Issue | v40 Status | v41 Status | v42 Verified |
|---|---|---|---|---|
| #1 | `drug_resolver` import crash (fuzzy_threshold 0.85 vs 0.60) | ❌ Broken | ✅ Fixed | ✅ **VERIFIED** |
| #2 | `drugbank_parser` canonical_id NameError | ❌ Broken | ✅ Fixed | ✅ **VERIFIED** |
| #3 | `chk_gda_source` CHECK rejects DisGeNET rows | ❌ Broken | ✅ Fixed | ✅ **VERIFIED** |
| #4 | README inaccuracy (5/5 claims false) | ❌ Broken | ✅ Fixed | ✅ **VERIFIED** |
| #5 | `_classify_drug_protein_edge("substrate")` returns "unknown" | ❌ Broken | ✅ Fixed | ✅ **VERIFIED** |
| #6 | `clean_interactions` double-normalization (1000× error) | ❌ Broken | ✅ Fixed | ✅ **VERIFIED** |
| #7 | train/val/test fallback contamination | ❌ Broken | ✅ Fixed | ✅ **VERIFIED** |

## Verification Method

For each SEV1 issue, I:
1. **Read the actual source code** in the v41 codebase to confirm the fix is present
2. **Wrote a runtime test** that reproduces the original bug scenario
3. **Ran the test** and verified it passes
4. **Ran the full pipeline** end-to-end to confirm no regressions

The test suite is at `tests/test_v42_sev1_fixes.py` (11 test cases, all PASS).

## SEV1 #1: drug_resolver import crash — VERIFIED ✅

**File:** `phase1/entity_resolution/drug_resolver.py:418` + `phase1/entity_resolution/base.py:341`

**Fix verification:**
```python
# drug_resolver.py line 418
_FUZZY_THRESHOLD: float = 0.60

# base.py line 341
fuzzy_threshold: float = 0.60

# drug_resolver.py line 5522-5526 — sync check passes
if _FUZZY_THRESHOLD != defaults.fuzzy_threshold:
    raise RuntimeError(...)  # 0.60 == 0.60, no raise
```

**Runtime test:**
```
✅ PASS [SEV1#1] drug_resolver imports cleanly;
   _FUZZY_THRESHOLD=0.6 == ResolverConfig.fuzzy_threshold=0.6
```

## SEV1 #2: drugbank_parser canonical_id NameError — VERIFIED ✅

**File:** `phase2/drugos_graph/drugbank_parser.py:3744` + `:3938`

**Fix verification:**
```python
# Line 3744 (drugbank_to_target_edges)
canonical_id = drug.inchikey if drug.inchikey else drug.drugbank_id

# Line 3938 (drugbank_to_interaction_edges)
canonical_id = drug.inchikey if drug.inchikey else drug.drugbank_id
```

**Runtime test:**
```
✅ PASS [SEV1#2] drugbank_to_target_edges → 1 edges, src_id='ABCDEFGHIJKLMNOPQ'
   drugbank_to_interaction_edges → 1 edges, src_id='ABCDEFGHIJKLMNOPQ'
```
(src_id correctly set to the inchikey, not NameError)

## SEV1 #3: chk_gda_source CHECK constraint — VERIFIED ✅

**Files:** `phase1/database/migrations/001_initial_schema.sql:920-926` + `phase1/database/models.py:1504-1508` + new `phase1/database/migrations/010_loosen_chk_gda_source_for_disgenet_subsources.sql`

**Fix verification:**
```sql
-- Migration 001 (line 920-926)
CONSTRAINT chk_gda_source
    CHECK (
        source IS NULL
        OR source = 'omim'
        OR source = 'disgenet'
        OR source LIKE 'disgenet|_%' ESCAPE '|'
    ),

-- ORM models.py (line 1504-1508)
CheckConstraint(
    "source IS NULL OR source = 'omim' OR source = 'disgenet' "
    "OR source LIKE 'disgenet|_%' ESCAPE '|'",
    name="chk_gda_source",
),

-- Migration 010 (new file) — applies the same loosened constraint
-- to existing PostgreSQL DBs.
```

**Runtime test:**
```
✅ PASS [SEV1#3] chk_gda_source accepts all disgenet_<subsrc> + bare disgenet
   + omim + NULL; rejects chembl + drugbank (8/8 cases pass)
```

## SEV1 #4: README inaccuracy — VERIFIED ✅

**File:** `README.md` (lines 1-50)

**Fix verification:**
All 6 headline claims now match runtime reality:
- ✅ "67 nodes and 66 edges" (was "40 nodes / 37 edges")
- ✅ "Bridge version: 1.1.0" (was "1.0.0")
- ✅ "12 Phase 1 source CSVs" (was "3 sources")
- ✅ "exits with code **4**" (was "exit code 0")
- ✅ "10 distinct edge types" (matches runtime)
- ✅ "zero errors and exit code 0" for dry-run (matches runtime)

**Runtime test:**
```
✅ PASS [SEV1#4] README has all 6 correct headline claims (6/6)
```

## SEV1 #5: substrate misclassification — VERIFIED ✅

**File:** `phase2/drugos_graph/phase1_bridge.py:1622-1623` + `:2132`

**Fix verification:**
```python
# Line 1622-1623 (_classify_drug_protein_edge)
if "substrate" in a:
    return "metabolized_by"

# Line 2132 (edge_buckets includes metabolized_by key)
"metabolized_by": [],
```

**Runtime test:**
```
✅ PASS [SEV1#5] _classify_drug_protein_edge: substrate → metabolized_by,
   agonist|positive modulator → activates (12/12 cases pass)
✅ PASS [SEV1#5b] edge_buckets includes 'metabolized_by' key (prevents KeyError)
```

## SEV1 #6: clean_interactions double-normalization — VERIFIED ✅

**File:** `phase1/cleaning/deduplicator.py:4249` + `:4265` + `:4208-4229`

**Fix verification:**
```python
# Line 4249 — update activity_units to "nM" after normalization
out[activity_units_column] = "nM"

# Line 4265 — pass normalize_units=False to dedup_interactions
_effective_normalize_units = normalize_units and not _v41_already_normalized

# Lines 4208-4229 — capture censor flags from original string-form value
def _detect_censor(val: Any) -> str:
    if s.startswith(">"): return ">"
    if s.startswith("<"): return "<"
    if s.startswith("~"): return "~"
    return ""
```

**Runtime test:**
```
✅ PASS [SEV1#6a] activity_units updated to 'nM' after normalization (was 'uM')
✅ PASS [SEV1#6b] activity_value in correct nM range (no 1000× error): [10000.0, 10000.0, 50000.0]
✅ PASS [SEV1#6c] censor flag preserved: activity_censor='>' (was lost before v41 fix)
```

## SEV1 #7: train/val/test fallback contamination — VERIFIED ✅

**File:** `phase2/drugos_graph/run_pipeline.py:5241-5257` + `:5279-5284`

**Fix verification:**
```python
# Lines 5241-5257 — fallback uses DISJOINT indices
if n >= 3:
    train_idx_list = list(range(n - 2))  # [0, 1, ..., n-3]
    val_idx_list = [n - 2]                # [n-2]
    test_idx_list = [n - 1]               # [n-1]
elif n == 2:
    train_idx_list = [0]
    val_idx_list = [1]
    test_idx_list = []
else:
    train_idx_list = [0]
    val_idx_list = []
    test_idx_list = []

# Lines 5279-5284 — defense-in-depth safety net
_train_set = set(train_idx_list)
_val_set = set(val_idx_list) - _train_set
_test_set = set(test_idx_list) - _train_set - _val_set
```

**Runtime test:**
```
✅ PASS [SEV1#7] train/val/test fallback uses DISJOINT indices for all n values
   (5/5 cases pass, no contamination)
```

## Integration Test — VERIFIED ✅

**Test:** `python run_unified.py --no-full-pipeline`

```
✅ PASS [INTEG] run_unified.py --no-full-pipeline exits 0 with 67 nodes / 66 edges
```

**Full pipeline test:** `python run_unified.py` (with `DRUGOS_ALLOW_LAUNCH_FAIL=1`)
- Exit code: 4 (V1 launch criteria NOT MET — by design for toy fixture)
- Total time: 38.7s
- Bridge: 67 nodes, 66 edges, 12 sources, 10 edge types
- TransE training: ran end-to-end, best_val_auc=0.602, held_out_auc=0.536
- No crashes, no NameErrors, no RuntimeErrors

## Test Suite Summary

```
═══════════════════════════════════════════════════════════════════
  SEV1-CRITICAL VERIFICATION TEST SUITE (v42)
  Proves all 7 SEV1 fixes from v40 audit are working
═══════════════════════════════════════════════════════════════════

  PASSED: 11
  FAILED: 0
  SKIPPED: 0

✅ ALL 7 SEV1-CRITICAL FIXES VERIFIED — codebase is v42-ready.
   Phase 1 ↔ Phase 2 connectivity: 100% (verified by integration test)
```

## Final Verdict

**ALL 7 SEV1-CRITICAL bugs from the v40 forensic audit report are FIXED and VERIFIED.**

The codebase now:
- ✅ Imports `drug_resolver` without crashing (SEV1 #1)
- ✅ Parses DrugBank XML without NameError (SEV1 #2)
- ✅ Loads DisGeNET rows into PostgreSQL/SQLite without CHECK violation (SEV1 #3)
- ✅ Has accurate README claims matching runtime (SEV1 #4)
- ✅ Classifies substrate drugs as `metabolized_by` (SEV1 #5)
- ✅ Normalizes activity values without 1000× error (SEV1 #6)
- ✅ Splits train/val/test without contamination (SEV1 #7)
- ✅ Runs end-to-end with 67 nodes / 66 edges / 12 sources / 10 edge types
- ✅ Phase 1 ↔ Phase 2 connectivity: 100% (verified by integration test)

The test suite `tests/test_v42_sev1_fixes.py` provides ongoing regression protection — any future change that re-introduces one of these 7 bugs will be caught immediately.
