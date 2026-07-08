"""v9 forensic audit fixes — regression test suite.

This package contains root-level regression tests for every P0/P1 fix
applied in response to the DrugOS v8 Forensic Audit Report. Each test
verifies the fix is FUNCTIONALLY correct (not just syntactically present)
by actually invoking the fixed code path and checking the output.

Audit findings covered:
  F1 / F4.1   — DisGeNET disease_id regexes accept prefixed format
  F2 / F4.2   — STRING data passed as string_df= kwarg (not 2nd positional)
  F3 / F5.1   — OMIM loader edge emitter strips OMIM: prefix from Gene IDs
  F4 / F6.1.1 — step11 passes val_triples + negative_sampler to train_transe
  F5 / F7.4   — Mixed-type node list split by label before load_nodes_batch
  F6 / F5.2.3 — STITCH src_id uses f"CID{int(cid)}" format
  F7 / 7.6    — AUC thresholds unified to 0.85
  F3.1        — _quarantine_gda_rows path resolves relative; raises on failure
  F3.2        — _pre_validate_gda quarantines before DB round-trip
  F3.3        — Migration 006 backfills is_withdrawn from DrugBank groups
  F3.4        — Standalone DAGs disabled (no Sunday double-ingest)
  F3.5        — DELETE FROM (not TRUNCATE TABLE) for SQLite support
  F3.6        — protein_id in ORM + EXPECTED_SCHEMA (no drift)
  F3.7        — Migration 003 swaps misordered PPI rows (UPDATE not DELETE)
  F3.8        — InChIKey regex consistent across all 4 modules
  F3.10/F4.4  — DrugBank DAG depends on OMIM; hard error on missing OMIM CSV
  F4.3        — DisGeNET gene_symbol regex tightened to HGNC convention
  F4.5        — MaxResponseSizeExceeded caught BEFORE HttpClientError
  F4.6        — _count_gz_csv_records streams (no OOM on large gz)
  F4.7        — pd.to_numeric strips NCBIGene: prefix before coerce
  F4.8        — STRING ID regex tightened to ENSP only
  F4.9        — OMIM ID format unified: DisGeNET preserves OMIM: prefix
  F4.10       — ProteinResolver validates gene_symbol against HGNC convention
  F5.2.1      — UniProt src_id strips uniprot: prefix
  F5.2.2      — DrugBank interaction edges emit src_id/dst_id
  F5.2.4      — GEO dst_id strips URI prefix (bare UBERON_xxxxx)
  F5.2.5      — ClinicalTrials uses tested_for rel_type; prefixed src_id
  F5.2.6      — OpenTargets orphan fallback translates MONDO_ → MONDO:
  F5.2.7      — _get_default_crosswalk() actually called in entity_resolver
  F5.2.8      — SIDER doctest tells truth about src_id type (no +SKIP lie)
  F6.1.2      — _check_v1_launch_criteria checks best_val_auc AND held_out_auc
  F6.3.4      — KGNegativeSampler class with correct API for TransE training
  F6.3.6      — step11 passes test_triples; held_out_auc computed
  F7.8        — ID_PATTERNS raises UnknownLabelError (no silent bypass)
  BUG-C-010   — Synthetic Gaussian CI fallback removed (raises)
  BUG-E-008   — Exit codes 2/3/4 implemented
"""
