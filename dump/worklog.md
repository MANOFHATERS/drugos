---
Task ID: v40-master-forensic-fix
Agent: main (Super Z)
Task: Install real dependencies (torch, neo4j, torch-geometric) and fix REAL runtime bugs found by actual end-to-end pipeline run

HONEST ASSESSMENT:
Previous sessions wrote test scripts that checked for code presence, not runtime
behavior. This session I INSTALLED the actual dependencies (torch 2.12.1+cpu,
neo4j 6.2.0, torch-geometric 2.8.0) and ran the REAL pipeline end-to-end. Two
REAL runtime bugs were found and fixed — both were introduced by previous "fix"
sessions and would have crashed any real run.

Work Log:
- INSTALLED torch 2.12.1+cpu, neo4j 6.2.0, torch-geometric 2.8.0 into the venv.
  These were the missing dependencies that caused "No module named 'torch'" and
  "No module named 'neo4j'" crashes. The pipeline can now actually train TransE
  and connect to Neo4j.

- pyg_builder.py (FORENSIC v40 ROOT FIX — Step 9 "too many values to unpack"):
  The v37 "vectorized edge dedup" fix had TWO bugs:
  1. Redundant first torch.unique call returned 1 value but was unpacked into 2
     variables → "too many values to unpack (expected 2)" ValueError crashed
     Step 9 (PyG build) on every run.
  2. The scatter_reduce_ used -1 as the initial sentinel, but with amin reduction
     and include_self=True, -1 would win as the minimum for every index, producing
     all -1s → ALL 66 edges were silently dropped → HeteroData had 0 edges.
  Fixed: removed redundant torch.unique call; changed sentinel from -1 to a large
  value (edge_index.size(1) + 1) so amin keeps real indices.

REAL END-TO-END VERIFICATION (with torch + neo4j installed):
- Ran: python run_unified.py --phase1-dir phase1/processed_data
- Step 1-2: bridge loads 11 CSVs + entity_mapping.csv → 67 nodes, 66 edges
- Step 8: entity resolution loads 8 Phase 1 entity_mappings, completes in 0.6s
- Step 9: PyG HeteroData built: 67 nodes, 66 edges (was 0 edges before fix)
- Step 10: 7 positive pairs, 18 negative pairs extracted
- Step 11: TransE trained 100 epochs (early-stopped at 55), best_val_auc=0.593
- Step 11: held-out evaluation: AUC=0.482 (8 test triples)
- V1 criteria: NOT PASSED (correct — toy fixture is too small for 0.85 AUC)

REAL V1 CRITERIA OUTPUT:
  all_sources_loaded: True
  sources_loaded_count: 12
  total_nodes: 67
  total_edges: 66
  transe_best_val_auc: 0.593 (ACTUALLY TRAINED)
  transe_held_out_auc: 0.482
  pipeline_ran_end_to_end: True
  graph_scale_meets_threshold: False (correct — toy has 67 nodes, needs 300K)
  auc_meets_threshold: False (correct — 0.59 < 0.85, toy too small)
  passed: False (correct — toy fixture should NOT pass V1)

Stage Summary:
- Installed real ML dependencies (torch, neo4j, torch-geometric)
- Fixed 2 REAL runtime bugs that crashed the actual pipeline
- Pipeline now runs COMPLETELY end-to-end: bridge → entity resolution →
  PyG build → training data → TransE training → evaluation → V1 criteria
- TransE ACTUALLY TRAINS (was impossible before — torch was missing)
- HeteroData has ALL 66 edges (was 0 — scatter_reduce bug dropped them all)
- The toy fixture correctly FAILLS V1 (67 nodes, 0.59 AUC — too small)
- This is the FIRST session where the pipeline actually ran end-to-end with
  real TransE training. All previous sessions' "tests" were tautological.
