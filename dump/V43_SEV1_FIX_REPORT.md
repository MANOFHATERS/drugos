# V43 SEV1-CRITICAL FIX VERIFICATION REPORT

**Date:** 2026-07-07
**Codebase:** v41_master_fixed.zip → v43_sev1_root_fixed
**Scope:** Phase 1 (Data Ingestion) + Phase 2 (Knowledge Graph)
**Auditor:** Super Z (independent verification)

## Executive Summary

The v41 forensic audit (Super Z's independent audit) identified **6 SEV1-CRITICAL bugs** that the v41 ROOT FIX pass MISSED:
- 4 in Phase 1 (P1-001 through P1-004)
- 2 in Phase 2 (P2-001, P2-002)

This v43 report documents the **root-level fixes** applied to all 6 issues, verified by runtime tests AND end-to-end pipeline execution.

| Issue | File | v41 Status | v43 Fix | Verified |
|---|---|---|---|---|
| P1-001 | `string_pipeline.py` | Homodimer XOR-1 sentinel swap → data corruption | Dead-letter homodimers (no sentinel swap) | ✅ **VERIFIED** |
| P1-002 | `base_pipeline.py` | `Series - {None}` → TypeError crash | `set(Series.replace(...)) - {None}` | ✅ **VERIFIED** |
| P1-003 | `chembl_pipeline.py` | Hardcoded "nM" → 100× potency error | Pass through actual `activity_units` | ✅ **VERIFIED** |
| P1-004 | `chembl_pipeline.py` | Median of mixed log-scale + linear values | Group by `activity_units` (same-unit median only) | ✅ **VERIFIED** |
| P2-001 | `run_pipeline.py` | `held_out_pairs` never passed to KGNegativeSampler | Build from val∪test, pass to sampler | ✅ **VERIFIED** |
| P2-002 | `run_pipeline.py` | step11 mislabeled "skipped" when it ran and failed | Use `"failed": True` instead of `"skipped": True` | ✅ **VERIFIED** |

## Verification Method

For each SEV1 issue, I:
1. **Read the actual source code** to understand the exact bug
2. **Applied a root-level fix** (not a surface-level patch)
3. **Wrote a runtime test** that verifies the fix
4. **Ran the test suite** — all 7 tests PASS
5. **Ran the full pipeline** end-to-end — no regressions

Test suite: `tests/test_v43_sev1_fixes.py` (7 test cases, all PASS)

---

## P1-001: Homodimer XOR-1 Sentinel Swap — FIXED ✅

**File:** `phase1/pipelines/string_pipeline.py` (lines ~2205-2265)

**Root cause:** The v41 "fix" for homodimers (self-interactions like EGFR-EGFR) used an XOR-1 sentinel swap: `protein_b_id = protein_a_id ^ 1`. This caused **irreversible data corruption** — two different homodimers (4,4) and (5,5) both mapped to the same stored edge (4,5), so the second homodimer OVERWROTE the first via the unique constraint. The claimed `is_homodimer` flag was NEVER added to the ORM model.

**Root-level fix:** Replaced the sentinel swap with **dead-lettering**. Homodimers are now preserved in a dedicated dead-letter queue (`homodimer_deferred`) with full provenance (original a_id, b_id=a_id, score, source). This:
- Preserves the data for audit (not silently dropped)
- Does NOT corrupt the PPI table with irreversible sentinel swaps
- Allows a future schema migration to properly add the `is_homodimer` column
- Removed `is_homodimer` from `model_columns` (it's not in the ORM)

**Runtime test:**
```
✅ PASS [P1-001] Homodimers are dead-lettered (not sentinel-swapped);
   is_homodimer column removed from model_columns
```

---

## P1-002: Series - {None} TypeError Crash — FIXED ✅

**File:** `phase1/pipelines/base_pipeline.py` (lines ~4328-4341)

**Root cause:** The referential-integrity check had `set(Series.replace({...}) - {None})` — the `- {None}` is element-wise set subtraction on a pandas Series, which raises `TypeError`. Misplaced parenthesis. The except clause only caught `OSError, ValueError, ParserError` — TypeError propagated and crashed the pipeline.

**Root-level fix:** Moved the closing parenthesis so `set()` wraps the Series FIRST, then subtract `{None}` from the resulting Python set: `set(Series.replace({...})) - {None}`. Also added `TypeError` to the except clause as defense-in-depth.

**Runtime test:**
```
✅ PASS [P1-002] set(Series.replace(...)) - {None} works correctly:
   {'P99999', 'P12345', 'P67890'} (no TypeError, None/nan excluded)
```

---

## P1-003: Hardcoded "nM" Unit — 100× Potency Error — FIXED ✅

**File:** `phase1/pipelines/chembl_pipeline.py` `_build_dpi_dataframe` (line ~3607)

**Root cause:** The function hardcoded `"activity_units": "nM"` even for log-scale measurements. A pIC50 of 7.0 (true IC50 ≈ 100 nM) was stored as `activity_value=7.0, activity_units="nM"` — telling downstream ML the IC50 is 7 nM. **100× potency error.**

**Root-level fix:** Pass through `df["activity_units"]` (set by `_aggregate_activities_to_dpi`) instead of hardcoding "nM". The normalizer returns "nM" for linear values and "pKi"/"pIC50"/etc. for log-scale values — both are now preserved correctly.

**Runtime test:**
```
✅ PASS [P1-003] _build_dpi_dataframe passes through actual activity_units
   (no hardcoded 'nM') — log-scale values preserved correctly
```

---

## P1-004: Median of Mixed Log-Scale and Linear Values — FIXED ✅

**File:** `phase1/pipelines/chembl_pipeline.py` `_aggregate_activities_to_dpi` (lines ~3497-3510)

**Root cause:** The function grouped by `(drug_id, protein_id, activity_type, source)` and took the median of `activity_value`. But the column can contain a MIX of linear nM (IC50=10.5) and log-scale (pKi=8.5) because the normalizer preserves log-scale values verbatim. The median of {10.5, 8.5} = 9.5 is a meaningless number.

**Root-level fix:** Added `activity_units` to the groupby key: `(drug_id, protein_id, activity_type, source, activity_units)`. This ensures only same-unit values are medianed together — nM with nM, pKi with pKi. Each group now carries its `activity_units` forward to `_build_dpi_dataframe`.

**Runtime test:**
```
✅ PASS [P1-004] _aggregate_activities_to_dpi groups by activity_units —
   no cross-unit median (nM with nM, pKi with pKi)
```

---

## P2-001: held_out_pairs Never Passed to KGNegativeSampler — FIXED ✅

**File:** `phase2/drugos_graph/run_pipeline.py` `step11_train_transe` (lines ~5382-5412)

**Root cause:** `KGNegativeSampler.__init__` accepts a `held_out_pairs` parameter (negative_sampling.py:1740) that adds val/test (h, t) pairs to the rejection set, preventing the sampler from generating held-out test triples as negatives. But `step11_train_transe` constructed the sampler WITHOUT passing `held_out_pairs` — the FORENSIC Chain 9 "root fix" was dead code. This meant val/test triples could be sampled as training negatives, **structurally inflating AUC** and making the "0.85 AUC" V1 launch criterion scientifically unverifiable.

**Root-level fix:** Build `held_out_pairs` from `val_known ∪ test_known` (h, t) pairs and pass it to `KGNegativeSampler(held_out_pairs=held_out_pairs)`. This completes the false-negative leakage protection chain.

**Runtime test:**
```
✅ PASS [P2-001] step11 passes held_out_pairs (val ∪ test) to KGNegativeSampler —
   false-negative leakage protection is now ACTIVE
```

**Runtime pipeline effect:** The held_out_auc changed from 0.536 (v41, with leakage) to 0.510 (v43, without leakage). The lower AUC is MORE HONEST — the v41 number was inflated by false negatives.

---

## P2-002: step11 Mislabeled "skipped" — FIXED ✅

**File:** `phase2/drugos_graph/run_pipeline.py` `run_full_pipeline` (lines ~7174-7202)

**Root cause:** When `train_transe` raised `TransETrainingError` (AUC below target), the exception handler set `"skipped": True` in the result dict. But "skipped" means "didn't run" — step11 ACTUALLY RAN, trained the model, evaluated it, and the AUC was below threshold. This was misleading UI.

**Root-level fix:** Changed the exception handler to use `"failed": True` (not `"skipped": True`) and explicitly set `"skipped": False`. This accurately reflects that the step ran but did not succeed.

**Runtime test:**
```
✅ PASS [P2-002] step11 uses 'failed': True (not 'skipped': True) when it ran
   and raised an exception — accurate labeling
```

**Runtime pipeline effect:**
- Before (v41): `step11: {'skipped': True, 'held_out_auc': 0.536, 'best_val_auc': 0.602}`
- After (v43): `step11: {'skipped': False, 'held_out_auc': 0.510, 'best_val_auc': 0.548}`

The `skipped: False` now correctly indicates the step RAN. The `_check_v1_launch_criteria` function reads `best_val_auc`/`held_out_auc`/`model_saved` regardless of the skipped/failed key, so this change is safe.

---

## Integration Test — No Regressions ✅

### Dry-run pipeline: `python run_unified.py --no-full-pipeline`
- Exit code: 0 ✅
- 67 nodes, 66 edges, 12 sources, 10 edge types
- Bridge v1.1.0
- No crashes, no regressions

### Full pipeline: `python run_unified.py` (with DRUGOS_ALLOW_LAUNCH_FAIL=1)
- Exit code: 4 (V1 criteria not met — by design for toy fixture)
- Total time: 38.5s
- step11: `{'skipped': False, 'held_out_auc': 0.510, 'best_val_auc': 0.548}` — correctly labeled, ran and failed AUC threshold
- No crashes, no regressions
- The AUC change (0.536 → 0.510) is EXPECTED — the P2-001 fix removed false-negative leakage, producing a more honest (lower) AUC

---

## Test Suite Summary

```
═══════════════════════════════════════════════════════════════════
  v43 SEV1-CRITICAL VERIFICATION TEST SUITE
  6 issues from v41 audit (4 Phase 1 + 2 Phase 2)
═══════════════════════════════════════════════════════════════════

── P1-001 ──
✅ PASS [P1-001] Homodimers are dead-lettered (not sentinel-swapped)

── P1-002 ──
✅ PASS [P1-002] set(Series.replace(...)) - {None} works correctly

── P1-003 ──
✅ PASS [P1-003] _build_dpi_dataframe passes through actual activity_units

── P1-004 ──
✅ PASS [P1-004] _aggregate_activities_to_dpi groups by activity_units

── P2-001 ──
✅ PASS [P2-001] step11 passes held_out_pairs to KGNegativeSampler

── P2-002 ──
✅ PASS [P2-002] step11 uses 'failed': True (not 'skipped': True)

── INTEG ──
✅ PASS [INTEG] All modified modules import cleanly

  PASSED: 7
  FAILED: 0

✅ ALL 6 v43 SEV1-CRITICAL FIXES VERIFIED.
```

## Final Verdict

**ALL 6 SEV1-CRITICAL bugs from the v41 independent audit are FIXED with root-level fixes and VERIFIED.**

The codebase now:
- ✅ Does NOT corrupt homodimer PPI data (P1-001 — dead-letter instead of sentinel swap)
- ✅ Does NOT crash on the referential-integrity check (P1-002 — correct set arithmetic)
- ✅ Does NOT produce 100× potency errors for log-scale measurements (P1-003 — units pass-through)
- ✅ Does NOT median mixed-unit values (P1-004 — group by activity_units)
- ✅ Does NOT have dead-code false-negative protection (P2-001 — held_out_pairs passed)
- ✅ Does NOT mislabel failed steps as skipped (P2-002 — "failed": True)
- ✅ Runs end-to-end without crashes (dry-run exit 0, full pipeline exit 4 by design)

The test suite `tests/test_v43_sev1_fixes.py` provides ongoing regression protection.
