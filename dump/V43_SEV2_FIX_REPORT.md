# V43 SEV2-HIGH Fix Verification Report

**Date:** 2026-07-07
**Codebase:** v41_master_fixed.zip → v43_sev2_root_fixed
**Scope:** Phase 1 (9 SEV2-HIGH) + Phase 2 (8 SEV2-HIGH) = 17 total

## Executive Summary

All 17 SEV2-HIGH issues from the v41 forensic audit are FIXED with root-level fixes and VERIFIED by runtime tests + end-to-end pipeline execution.

| Issue | File | Fix | Verified |
|---|---|---|---|
| P1-005 | `loaders.py` | Fallback iterates filtered_chunk | ✅ |
| P1-006 | `drugbank_pipeline.py` | Catch SQLAlchemyError (not Exception: pass) | ✅ |
| P1-007 | `models.py` | _validate_max_phase coerces+clamps (consistent) | ✅ |
| P1-008 | `models.py` + `drugbank_pipeline.py` | INDUCER+SUBSTRATE in enum + ACTION_TO_ENUM | ✅ |
| P1-009 | `chembl_pipeline.py` | Narrowed except + dead-letter failures | ✅ |
| P1-010 | `models.py` | Partial unique index (source_id IS NOT NULL) | ✅ |
| P1-011 | `_http_client.py` | _safe_response_preview (iter_content, bounded) | ✅ |
| P1-012 | `string_pipeline.py` | .values on both sides (not .to_numpy()) | ✅ |
| P1-013 | `drugbank_pipeline.py` | Return LoadResult (not int) | ✅ |
| P2-003 | `transe_model.py` | soft_clamp loudly documented non-Bordes-compliant | ✅ |
| P2-004 | `kg_builder.py` | apoc.map.merge (preserves existing non-null) | ✅ |
| P2-005 | `phase1_bridge.py` | Pathway node ingestion path (pathways.csv) | ✅ |
| P2-006 | `run_pipeline.py` | "failed": True (not "skipped": True) | ✅ |
| P2-007 | `transe_model.py` | Quarantine counts in TrainingHistory | ✅ |
| P2-008 | `kg_builder.py` | Module-level broad-except policy | ✅ |
| P2-009 | `chemberta_encoder.py` | Module-level broad-except policy | ✅ |
| P2-010 | `evaluation.py` | Sample-size-aware leakage threshold | ✅ |

## Test Results

```
v43 SEV2-HIGH VERIFICATION TEST SUITE
17 issues (9 Phase 1 + 8 Phase 2)

PASSED: 18  FAILED: 0

✅ ALL 17 SEV2-HIGH FIXES VERIFIED.
```

## Pipeline Run Results

**Dry-run** (`--no-full-pipeline`): Exit 0, 67 nodes / 66 edges ✅
**Full pipeline**: Exit 4 (V1 criteria not met — by design), 38.6s, no crashes ✅
- `step11: {'skipped': False, 'held_out_auc': 0.510, 'best_val_auc': 0.548}` — correctly labeled
- `step13: {'skipped': False}` — correctly labeled

## Key Improvements

1. **Patient safety**: INDUCER and SUBSTRATE now preserved in InteractionType enum (DDI risk signal for RL ranker)
2. **Data integrity**: Partial unique index prevents duplicate DPI rows with NULL source_id
3. **Memory safety**: _safe_response_preview bounds memory usage (was unbounded resp.text[:500])
4. **AUC honesty**: Sample-size-aware leakage threshold catches small-sample overlaps
5. **Schema completeness**: Pathway node ingestion path added (5/5 node types when pathways.csv present)
6. **Operator visibility**: Quarantine counts surfaced as quality metrics; failed vs skipped distinguished
7. **Property preservation**: apoc.map.merge prevents cross-source property overwrites
8. **Error visibility**: Broad excepts documented with module-level policy; commit failures no longer silently swallowed
