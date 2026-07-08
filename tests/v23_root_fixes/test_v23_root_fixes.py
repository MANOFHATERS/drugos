"""v22 ROOT FIX verification tests.

Each test verifies ONE specific audit finding's root-level fix by reading
the ACTUAL production code (not test stubs). The user's complaint was that
previous sessions CLAIMED fixes but cross-verification showed issues
remained. These tests inspect the real source files to ensure the fixes
are present in the production code path.

Audit findings covered (all 30+ from v20 forensic audit):
  P0-1: NameError on phase1_processed_dir in step7_additional_sources
  P0-2: argparse lockout on --skip-download (BooleanOptionalAction)
  P0-3: chembl/drugbank/string/uniprot loaders consume Phase 1 CSVs
  P0-4: real negative filtering in negative_sampling + transe_model
  P1-5: SIDER stubs replaced with real parsers
  P1-6: NCBI fake verification replaced with real API call
  P1-7: three InChIKey validators unified
  P1-8: three UniProt regexes + three gene-symbol regexes unified
  P2-9: 002_bug_fixes_migration.sql BEGIN/COMMIT wrapper
  P2-10: rollback_migration sidecars for all 6 migrations
  P2-11: dead-letter queue RLock
  P2-12: no within-class duplicate method definitions
  X-1: kg_builder edge-property stripping (FLAT vs nested)
  X-2: bridge EC50/AC50 not 'activates'
  X-3: bridge ID emission (CHEMBL_TGT_ accepted, SYM: prefix)
  X-4: STITCH edge type not collapsed to 'binds'
  X-5: chembl_loader deterministic SQLite selection
  X-6: evaluation.py filtered MRR
  X-7: negative_sampling relation_idx passed by caller
  X-8: loaders gene_symbol quarantine (not silent drop)
  X-9: loaders protein chunk filtering (asymmetry fixed)
  X-10: run_migrations type contract (list[dict[str,str]])
  X-11: chembl_pipeline is_fda_approved stale log message updated
  X-12: omim_pipeline dead code removed
  X-13: _cached_parse_drkg dead function removed
  X-14: normalizer watch_config / sign_output docstrings updated
  X-15: omim_pipeline HGNC strict-by-default in production
  X-16: disgenet/omim loaders freshness check
  X-17: pd.Timestamp.utcnow() deprecated call removed
  X-18: TransEModel.__init__ saves num_entities (held-out AUC bug)
  X-19: Dev-mode V1 launch criteria thresholds
"""
