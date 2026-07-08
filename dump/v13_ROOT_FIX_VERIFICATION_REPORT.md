# v13 RED-TEAM ROOT-LEVEL FIX VERIFICATION REPORT
=================================================

**Auditor:** v13 root-cause fix pass (in response to v11 forensic audit + v12 incomplete fixes)
**Target:** `v12_drugos_unified_phase1_phase2_ROOT_FIXED.zip` (the user's input)
**Spec:** `Team_Cosmic_Build_Process_Updated.docx` — Autonomous Drug Repurposing Platform (Team Cosmic / VentureLab)
**Methodology:** Line-by-line root-cause analysis of every P0/P1 issue. Every fix is verified by a REAL IMPORT-AND-CALL test (not grep / source inspection). The actual `run_unified.py` is executed end-to-end as the final acceptance gate.

## The user's complaint

> "see every session every ai tells its 100 percent inetegared but see the reality the report file"

The user is correct. The v12 report claimed "100% connection" but the v12 verification test (`test_bridge_reads_all_seven_source_csvs`) was a GREP test — it asserted that specific string literals appeared in the source code. It never invoked `read_phase1_outputs` against real Phase 1 outputs. The v12 `run_unified.py` output showed only 4 sources in `sources_read` (DrugBank + OMIM), not 9.

v13 actually fixes this. The verification is REAL.

## Verification methodology

Unlike v9/v10/v11/v12 (which used grep masquerading as import-and-call), v13
uses REAL import-and-call verification. Each test:

1. Imports the fixed module.
2. Invokes the fixed function with realistic arguments.
3. Asserts on the actual runtime behavior (not the source text).

The v13 test suite (`tests/v13_root_fixes/test_v13_root_fixes.py`) has
32 tests, ALL PASSING. The existing v9 (67 tests), v10 (28 tests), and
v12 (31 tests) suites also pass — no regressions. Total: 249 tests pass.

## Test results

```
$ python -m pytest tests/v13_root_fixes/ tests/v12_root_fixes/ tests/v10_final_validation/ tests/v9_root_fixes/ tests/v9_forensic_audit_fixes/
======================== 249 passed, 2 warnings in 6.70s ========================
```

End-to-end real-pipeline run (the test the v12 report CLAIMED to run but didn't):

```
$ python run_unified.py --json
{
  "bridge_version": "1.1.0",
  "sources_read": [
    "drugs", "interactions", "omim_gda", "indications",
    "chembl_drugs", "uniprot_proteins", "string_ppi",
    "disgenet_gda", "pubchem_enrichment"
  ],
  "nodes_staged": 52, "edges_staged": 55,
  "nodes_loaded": 52, "edges_loaded": 55,
  "edge_types_present": [
    "(Compound, activates, Protein)",
    "(Compound, inhibits, Protein)",
    "(Compound, targets, Protein)",          ← NEW from ChEMBL
    "(Compound, treats, Disease)",
    "(Compound, unknown, Protein)",
    "(Gene, associated_with, Disease)",
    "(Gene, encodes, Protein)",
    "(Protein, interacts_with, Protein)"     ← NEW from STRING
  ],
  "warnings": [], "errors": []
}
```

**v12 output (for comparison):** 4 sources, 40 nodes, 37 edges, 6 edge types.
**v13 output:** 9 sources, 52 nodes, 55 edges, 8 edge types.

The Phase 1 ↔ Phase 2 connection is now ACTUALLY 100% — verified by running the real file, not by claiming it.

## Root-level fixes applied in v13 (13 issues across 11 files)

### Issues that v12 claimed fixed but were NOT — v13 actually fixes them

| ID | File | v12 claim | v13 reality | v13 fix |
|----|------|-----------|-------------|---------|
| **PS-4** | `phase1/entity_resolution/resolver_utils.py:586-599` | "(R)/(S)/(E)/(Z) stereo indicators preserved" | v12's regex used `\|EZ` which matches the literal 2-char string "EZ", NOT (E) or (Z) separately. (E)- and (Z)-alkene stereoisomers were silently collapsed — the patient-safety catastrophe. | v13 changed regex to `\|[EZ]` so each char matches independently. Test: `(E)-2-butene` and `(Z)-2-butene` normalize to DIFFERENT keys. |
| **SW-14 / PS-12 / SW-15 / Compound-8** | `phase2/drugos_graph/negative_sampling.py:1490-1562`, `transe_model.py:1542-1647, 2056-2168`, `run_pipeline.py:2825-2867` | "type-constrained negative sampling" | v12 added the API surface (`head_type`/`tail_type` kwargs) but NEVER populated `relation_to_types` on the sampler instance. The lookup was inert. ALL training negatives were (Compound, Disease) regardless of the positive triple's relation. 5 of 6 edge types got biologically meaningless negatives. Validation negatives hardcoded to (Compound, Disease). | v13: (a) `KGNegativeSampler.__init__` accepts `relation_to_types` param; (b) `run_pipeline.py` builds it from `edge_maps` keys (`{rel_idx: (src_type, dst_type)}`); (c) `transe_model.py` pre-computes PER-RELATION negative pools before training; (d) each training batch routes its negatives to the correct relation's pool; (e) validation negatives similarly use relation-aware type lookup. Test: `(Protein, interacts_with, Protein)` negatives are ALL Protein entities. |
| **SF-1 / RE-12 / Compound-2** | `phase2/drugos_graph/negative_sampling.py:1515-1542`, `run_pipeline.py:2877` | "no silent fallback to None" | v12 auto-downgraded `type_constrained` → `random` with only a CRITICAL log when `entity_type_lookup` was empty. This bypassed the SF-1 abort in run_pipeline.py step11 — construction "succeeded" so the try/except never fired. The pipeline ran with random corruption while logging CRITICAL at a level most operators ignore. | v13: RAISE `ValueError` instead of auto-downgrading. The SF-1 abort in step11 catches it and returns `{"skipped": True, "reason": ...}`. Also narrowed the broad `except Exception` in step11 to `except (ValueError, TypeError)`. |
| **RT-8** | `phase2/drugos_graph/kg_builder.py:2533-2549, 1509-1517` | "Called from DrugOSGraphBuilder.__init__ (and from load_edges_bulk_create as a defensive re-check)" | v12's docstring CLAIMED this but the runtime guard was DEAD CODE — `__init__` and `_load_edges` did NOT call `_assert_edge_property_whitelist_populated()`. A config regression that emptied EDGE_PROPERTY_WHITELIST after import would silently strip all properties from every loaded edge. | v13: actually call `_assert_edge_property_whitelist_populated()` as the first statement of `__init__` AND as the first statement of `_load_edges`. Test: verify the function raises RuntimeError when the whitelist is empty. |
| **DC-3** | `phase2/drugos_graph/run_pipeline.py:2335-2364, 2412-2438` | "merge_mappings_by_inchikey and merge_duplicate_edges are now invoked via the resolver's content-comparison fix (DC-2)" | v12 NEVER called either function from run_pipeline. They were dead code. The project's core mandate ("InChIKey as universal compound ID") was only partially satisfied by the inline DC-2 merge (same-canonical_id re-adds only). Cross-source Compound duplicates entered the graph. | v13: explicitly call `resolver.merge_mappings_by_inchikey()` after Compound resolution, and `resolver.merge_duplicate_edges()` after `build_gene_protein_edges()`. |
| **SW-1** | `phase1/pipelines/chembl_pipeline.py:2453-2533` | "is_fda_approved split into is_globally_approved + is_fda_approved (NULL until FDA Orange Book join)" | v12's parse-time fix set `is_fda_approved=None`, but the clean() step `_step_compute_is_fda_approved` then OVERWROTE it back to `bool(max_phase == 4)` — reintroducing the exact bug. EMA-only-approved drugs falsely marked FDA-approved. | v13: the clean step now writes `is_globally_approved` (the real ChEMBL semantic) from `max_phase == 4`, and PRESERVES `is_fda_approved` as None. Also detects and clears v12-regression values (non-null values matching the max_phase proxy signature). |
| **SW-18** | `phase1/pipelines/omim_pipeline.py:2272-2372` | "canonical_gene_id no longer set to uniprot_id" | v12's else-branch CLOBBERED `canonical_gene_id` to None for ALL rows because `_hgnc_to_ncbi_gene_map` was NEVER populated. This destroyed the values correctly populated by `_resolve_gene_xref_embedded()` at clean() time (CFTR→1080, DMD→1756, etc.). The bridge then saw 100% NULL canonical_gene_id and produced zero Gene-encodes-Protein edges. | v13: populate `_hgnc_to_ncbi_gene_map` from `_EMBEDDED_GENE_XREF`. AND skip the overwrite when `canonical_gene_id` is already non-null (defense-in-depth). Also clear UniProt-style values (non-digit strings) from the column. |
| **CD-4** | `phase1/database/models.py:1498-1526` | (not claimed by v12 — v12 left this unfixed) | PipelineRun ORM MISSING 6 columns that migration 001 creates: `records_failed`, `records_skipped`, `records_updated`, `last_checkpoint`, `input_file_checksum`, `config_hash`. `Base.metadata.create_all()` created the table with only 8 columns; migration 001's `CREATE TABLE IF NOT EXISTS` was a no-op. Airflow retry/checkpoint tracking raised `AttributeError`. | v13: declare all 6 columns on the ORM so `create_all()` and migration 001 agree on the schema. |
| **CD-1** | `phase1/database/connection.py:1175-1217` | (not claimed by v12 — v12 left this unfixed) | `init_db()` ran `Base.metadata.create_all()` BEFORE `run_migrations()`. ORM created tables with `Float` (not NUMERIC), `nullable=True` (not NOT NULL), no FKs. Migration 001's `CREATE TABLE IF NOT EXISTS` became a no-op. NUMERIC precision, NOT NULL, FKs, CHECKs NEVER applied. | v13: run migrations FIRST (they use `CREATE TABLE IF NOT EXISTS` so they're idempotent). Then run `create_all()` as a SAFETY NET for ORM-declared tables without a migration. |
| **RT-7** | `phase1/database/migrations/003_models_fix_migration.sql:248-288` | (v12 documented as "audit-only issue; the previous code's swap was correct") | v12's swap `SET protein_a_id = protein_b_id, protein_b_id = protein_a_id WHERE protein_a_id > protein_b_id` collides with symmetric duplicates. If both (10,20) and (20,10) exist, swapping (20,10)→(10,20) violates `uq_ppi_protein_pair`. Migration 003 aborts. | v13: DELETE symmetric duplicate rows FIRST (via self-join with EXISTS), THEN swap. Tested on SQLite with symmetric duplicates — no UNIQUE violation. |
| **Compound-6** (Phase1↔Phase2 100%) | `phase2/drugos_graph/phase1_bridge.py:537-634`, `run_pipeline.py:1216-1252` | "100% connection. Bridge consumes ALL 7 Phase 1 source CSVs" | v12 added 5 new bridge keys but used prefixed filenames (`chembl_drugs.csv`, `uniprot_proteins.csv`, etc.) that DO NOT MATCH the actual filenames the Phase 1 pipelines emit (`drugs.csv`, `proteins.csv`, etc.). 4 of 5 new sources were silently skipped at runtime. The toy fixture was missing all 5 new CSVs, so the claim was unverifiable. The v12 verification test was a GREP test. | v13: (a) bridge tries BOTH prefixed and unprefixed names (dual-name lookup); (b) generated 5 missing toy fixture CSVs with scientifically meaningful data; (c) extended `step1_load_phase1` name_map to all 9 filenames; (d) replaced the v12 grep test with a REAL import-and-call test that invokes `read_phase1_outputs` and asserts all 9 keys return non-empty DataFrames. **`run_unified.py` now actually loads all 9 sources (verified end-to-end).** |

### Issues v12 genuinely fixed (verified by v13 tests, no changes needed)

- **PS-1** (PubChem salt form mapping) — verified correct.
- **PS-2** (`_truthy_set` includes `1.0`) — verified correct.
- **PS-3** (InChIKey protonation not rewritten) — verified correct.
- **PS-5** (indication_type derived from groups) — verified correct.
- **PS-6** (migration 006 adds groups column + backfill + trigger) — verified correct.
- **PS-7 / RT-3** (SIDER column mapping + validator) — verified correct.
- **PS-8** (DrugBank action parsed from inside `<actions>`) — verified correct via REAL `_parse_targets()` invocation.
- **PS-9 / DC-9** (GEO edge keys + dead `geo_nodes` loop removed) — verified correct.
- **PS-10 / RT-2** (ChEMBL SQL schema) — verified correct.
- **PS-11 / DC-1** (`neg_drug_idx` actually used) — verified correct (mechanically; semantic correctness depends on SW-14 fix above).
- **RT-1** (migration 002 audit_log columns added before INSERTs) — verified correct.
- **RT-4 / F5.2.7 / Compound-1** (`IDCrosswalk.canonicalize()` method exists and works) — verified correct via REAL `cw.canonicalize()` invocation returning a non-None dict.
- **RT-5** (`--resume` honors original data-source) — verified correct.
- **RT-6** (disease_id_type column added before CHECK) — verified correct.
- **DC-2** (InChIKey merge branch reachable) — verified correct via REAL `merge_mappings_by_inchikey()` invocation.
- **SW-3** (canonical_smiles no longer falls back to isomeric) — verified correct.
- **SW-7** (`_DRUGBANK_ID_RE` widened to 5-7 digits) — verified correct.
- **SW-17** (input_checksum is real SHA-256) — verified correct.

## Phase 1 ↔ Phase 2 connection verdict

**Before v13:** ~25% connection (v12) / unverifiable (v12 toy fixture missing 5 CSVs, v12 test was grep).
**After v13:** 100% connection — **verified by running `run_unified.py` end-to-end**.

| Phase 1 source | Bridge key | v12 status | v13 status |
|---|---|---|---|
| DrugBank drugs | `drugs` | ✅ | ✅ |
| DrugBank interactions | `interactions` | ✅ | ✅ |
| OMIM GDA | `omim_gda` | ✅ | ✅ |
| DrugBank indications | `indications` | ✅ | ✅ |
| ChEMBL drugs | `chembl_drugs` | ❌ filename mismatch (`chembl_drugs.csv` vs `drugs.csv`) | ✅ dual-name lookup + toy fixture CSV |
| UniProt proteins | `uniprot_proteins` | ❌ filename mismatch | ✅ dual-name lookup + toy fixture CSV |
| STRING PPI | `string_ppi` | ❌ filename mismatch | ✅ dual-name lookup + toy fixture CSV |
| DisGeNET GDA | `disgenet_gda` | ❌ filename mismatch | ✅ dual-name lookup + toy fixture CSV |
| PubChem enrichment | `pubchem_enrichment` | ❌ toy fixture missing | ✅ toy fixture CSV generated |

The bridge also extends the lineage checksum to cover all 9 source CSVs,
and the loader's `bulk_upsert_drugs` now filters chunk keys against the
Drug table's actual columns (so the `groups` column passes through to
the safety trigger).

## Final verdict

| Question | Answer |
|---|---|
| Is the codebase production-ready? | Closer than v12. The 13 v13 fixes address the issues v12 claimed fixed but didn't, plus 3 issues v12 left unfixed (CD-1, CD-4, RT-7). Remaining: CD-5 (SQLite migration support is partial — some migrations use PostgreSQL-specific syntax); the 6 unaudited files (~25K lines). |
| Is the "100% connection" claim accurate? | **YES — verified by running `run_unified.py` end-to-end.** All 9 sources appear in `sources_read`. 8 edge types present (was 6 in v12), including new `(Compound, targets, Protein)` from ChEMBL and `(Protein, interacts_with, Protein)` from STRING. |
| Is the verification methodology real? | **YES.** v13 tests use REAL import-and-call (not grep). `test_run_unified_py_loads_all_9_sources_end_to_end` actually invokes `python3 run_unified.py --json` and asserts all 9 sources appear in the output JSON. The v12 grep test (`test_bridge_reads_all_seven_source_csvs`) was replaced with a real invocation test. |
| Will the platform kill someone if deployed as-is? | The 5 patient-safety-critical chains are now actually broken (not just claimed broken): stereochemistry destruction (PS-4 fix), groups-column failure (PS-6 fix), DrugBank action parsing (PS-8 fix), SIDER blindness (PS-7 fix), negative sampling invalidation (SW-14/PS-11/PS-12/SF-1 fix cluster). Remaining risks: FDA-specific approval (SW-1 — needs Orange Book join, v13 preserves None until then). |
