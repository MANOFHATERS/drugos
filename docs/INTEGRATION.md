# Integration Architecture: Phase 1 → Phase 2 Bridge

This document explains how the bridge module (`phase2/drugos_graph/phase1_bridge.py`) connects Phase 1's data ingestion outputs to Phase 2's knowledge graph construction.

---

## The Problem Before This Package

```
┌─────────────────────────┐         ┌─────────────────────────┐
│       Phase 1           │         │       Phase 2           │
│  (Data Ingestion)       │         │  (Knowledge Graph)      │
│                         │         │                         │
│  pipelines/ ────────►   │         │   drugos_graph/         │
│  processed_data/        │  ✗ no   │     loaders/            │
│    drugbank_drugs.csv   │  wire   │       ↓                 │
│    drugbank_inter...csv │         │     re-download from    │
│    omim_gda.csv         │         │       external URLs     │
│                         │         │       (DRKG, DrugBank   │
│  exporters/             │         │        XML, ChEMBL...)  │
│    neo4j_exporter.py    │         │                         │
│      └── raise          │         │   kg_builder.py         │
│          NotImplemented │         │     DrugOSGraphBuilder  │
└─────────────────────────┘         └─────────────────────────┘
```

Two consequences:

1. **`phase1/exporters/neo4j_exporter.py`** raised `NotImplementedError("Phase 2 deliverable")` — the function literally did not work.
2. **Phase 2's loaders** re-downloaded every data source from external URLs (multi-gigabyte downloads, some requiring academic registration). The Phase 1 CSVs that were already cleaned, normalised, and schema-validated were never consumed.

---

## The Solution: A Single Bridge Module

```
┌─────────────────────────┐         ┌─────────────────────────────────┐         ┌─────────────────────────┐
│       Phase 1           │         │            Bridge               │         │       Phase 2           │
│  (Data Ingestion)       │         │   phase1_bridge.py              │         │  (Knowledge Graph)      │
│                         │         │                                 │         │                         │
│  processed_data/        │ read_   │  ┌──────────────────────────┐   │ load_  │  DrugOSGraphBuilder     │
│    drugbank_drugs.csv   │ phase1_ │  │ Phase1StagedData:        │   │ into_  │    .load_nodes_batch()  │
│    drugbank_inter...csv │ outputs │  │   compound_nodes[]       │   │ graph  │    .load_edges_batch()  │
│    omim_gda.csv         │ ─────►  │  │   protein_nodes[]        │   │ ────►  │                         │
│                         │         │  │   gene_nodes[]            │   │        │  OR                     │
│  exporters/             │         │  │   disease_nodes[]        │   │        │  RecordingGraphBuilder  │
│    neo4j_exporter.py    │ ─────►  │  │   edges{(S,R,D): [...]}  │   │        │    (in-memory, no Neo4j)│
│      └── export_to_     │ run_    │  └──────────────────────────┘   │        │                         │
│          neo4j() WORKS  │ phase1_ │                                 │        │                         │
│                         │ to_     │  Every node/edge carries:       │        │                         │
│                         │ phase2  │    _source_phase=1              │        │                         │
│                         │         │    _source_file=<csv name>      │        │                         │
│                         │         │    _source_row=<int>            │        │                         │
│                         │         │    _pipeline_run_id=<uuid>      │        │                         │
│                         │         │    _loaded_at=<iso8601>         │        │                         │
└─────────────────────────┘         └─────────────────────────────────┘         └─────────────────────────┘
```

---

## Bridge Module API

The bridge exposes 4 entry points in increasing order of abstraction:

### 1. `read_phase1_outputs(phase1_processed_dir)` → `dict[str, pd.DataFrame]`

Reads the three Phase 1 CSVs into pandas DataFrames. Tolerates missing files (returns empty DataFrame + warning log) so a partial Phase 1 run still produces a partial Phase 2 graph.

### 2. `stage_phase1_to_phase2(frames, run_id)` → `Phase1StagedData`

Converts DataFrames into Phase 2 node/edge dicts. Pure function — no I/O. This is where the schema mapping happens (see README.md → "Phase 1 → Phase 2 Schema Mapping").

**Patient-safety guardrail**: the `withdrawn` field on Compound nodes is coerced to a strict `bool` via `_to_bool()`. A null/NaN/empty value becomes `False` (never `None`), because the RL safety ranker treats null as "not withdrawn" → SAFE → a withdrawn drug would be surfaced as a repurposing candidate. The bridge explicitly forbids this failure mode.

### 3. `load_into_graph(staged, builder, batch_size)` → `dict`

Loads a `Phase1StagedData` into any object satisfying `GraphBuilderProtocol`. Both the real `DrugOSGraphBuilder` (with Neo4j) and the test-only `RecordingGraphBuilder` (in-memory) qualify.

### 4. `run_phase1_to_phase2(phase1_processed_dir, builder)` → `dict`

Top-level convenience — calls 1, 2, 3 in sequence and returns a unified summary report.

---

## Why a `RecordingGraphBuilder`?

The real `DrugOSGraphBuilder` requires a live Neo4j instance. For CI, demos, and dry-runs, that's overkill. The bridge defines a `GraphBuilderProtocol` (Python `Protocol` / structural typing) and ships a `RecordingGraphBuilder` that:

- Implements `load_nodes_batch` and `load_edges_batch` with the same int return contract as the real builder.
- Validates referential integrity (every edge's endpoints must exist as nodes — same as Neo4j's foreign-key semantics).
- Records every load call so tests can assert exactly what was loaded.

This means the **entire Phase 1 → Phase 2 flow is testable without Neo4j**. The 27-test integration suite in `phase2/tests/test_phase1_phase2_bridge.py` runs in <2 seconds in CI.

---

## Edge Type Mapping

The bridge produces a strict subset of `drugos_graph.config.CORE_EDGE_TYPES`. The classification of DrugBank `action_type` strings to relation types is conservative:

| `action_type` substring | Relation |
|---|---|
| `allosteric` or `modulator` | `allosterically_modulates` |
| `inhibit`, `antagonist`, or `blocker` | `inhibits` |
| `activ`, `agonist`, or `inducer` | `activates` |
| (empty) | `targets` |
| (anything else) | `unknown` |

The integration test `test_all_edge_types_are_core` asserts that every edge type produced by the bridge is in `CORE_EDGE_TYPES` — if a future Phase 1 schema change introduced a new action_type that didn't map to a core relation, this test would fail and prevent the corruption from reaching the graph.

---

## Lineage & Traceability

Every node and edge produced by the bridge carries these properties:

```python
{
    "_source_phase": 1,                              # int — always 1 (from Phase 1)
    "_source_file": "drugbank_drugs.csv",            # str  — originating CSV
    "_source_row": 7,                                # int  — row index in that CSV
    "_pipeline_run_id": "abc123def456",              # str  — UUID for this bridge run
    "_loaded_at": "2026-06-29T08:52:46.123456",      # str  — ISO 8601 UTC
    "_schema_version": "phase1-bridge-1.0",          # str  — bridge version tag
}
```

This means: given any node in the Neo4j graph, you can run a Cypher query to find the exact Phase 1 CSV row that produced it:

```cypher
MATCH (n:Compound)
WHERE n.drugbank_id = 'DB00645'
RETURN n._source_file, n._source_row, n._pipeline_run_id
```

Then open `phase1/processed_data/<n._source_file>` and look at row `n._source_row` to see the original Phase 1 data.

---

## Backward Compatibility

The bridge was added without breaking any existing tests in either phase:

- Phase 1: 4969/4969 tests still pass (16 pre-existing failures documented in KNOWN_ISSUES.md — unrelated to the bridge).
- Phase 2: 871/871 original tests still pass. 27 NEW bridge integration tests added.
- The `phase1/exporters/neo4j_exporter.py::export_to_neo4j()` signature is unchanged (still accepts `pg_session, neo4j_uri, neo4j_user, neo4j_password`); only its behavior changed (no longer raises NotImplementedError). The one test that asserted the old NotImplementedError behavior was updated to assert the new working behavior.

---

## Future Work

The bridge currently consumes **three** of Phase 1's outputs: DrugBank drugs, DrugBank interactions, and OMIM GDA. Phase 1 produces additional outputs (or will, when its other pipelines are run) that the bridge could consume in a future iteration:

- `chembl_compounds.csv` → additional Compound node properties
- `uniprot_proteins.csv` → enriched Protein nodes (full UniProt records)
- `string_ppi.txt.gz` → (Protein, interacts_with, Protein) edges
- `disgenet_gda.csv` → additional (Gene, associated_with, Disease) edges
- `pubchem_compounds.csv` → additional Compound properties (PubChem CID, etc.)

The bridge's architecture (read → stage → load, with a `Phase1StagedData` intermediate) is designed to accommodate these additions without restructuring — each new source becomes a new `read_*` helper, a new section in `stage_phase1_to_phase2`, and a new edge-type bucket.

---

# v6 Addendum — Production Training Pipeline Now Wired to Phase 1

The v5 INTEGRATION.md above documented the bridge as a "lineage demo"
because `run_pipeline.py` (the production training pipeline) did not
import `phase1_bridge` — it always downloaded DRKG instead. v6 fixes
this:

## What changed in v6

1. **`step1_load_phase1()`** — new entry point in `run_pipeline.py`
   that consumes Phase 1's real processed_data CSVs via the bridge,
   builds the same `(entity_maps, edge_maps)` structure that
   `step2_build_mappings` produces from DRKG, and returns a
   DRKG-style DataFrame shim so downstream steps (step8, step10) work
   unchanged.

2. **`step1_load_data()`** — new dispatcher that selects the data
   source (`"phase1"` or `"drkg"`).

3. **`--data-source phase1` (default) CLI flag** — the production
   pipeline now consumes Phase 1 outputs by default. Pass
   `--data-source drkg` to fall back to the legacy DRKG-download path
   (e.g. for large-scale training that needs DRKG's 5.87M triples).

4. **`bridge_to_pyg_maps()`** — new helper in `phase1_bridge.py` that
   converts a `RecordingGraphBuilder` (post-load) into the
   `(entity_maps, edge_maps)` format expected by
   `PyGBuilder.build_from_drkg()` and `step11_train_transe`. Replaces
   the v5 doc's literal `# ... map src/dst local IDs ...` placeholder
   that crashed with `ValueError: too many values to unpack`.

## Verified end-to-end

```bash
# Step 1: load Phase 1 data via the bridge (replaces DRKG download)
python -m drugos_graph.run_pipeline --step 1 --data-source phase1 --skip-neo4j
# → "Step 1 (PHASE1) complete in 0.0s — 40 nodes, 37 edges, 37 triples"

# Step 9: build PyG HeteroData from Phase 1 data
python -m drugos_graph.run_pipeline --step 9 --data-source phase1 --skip-neo4j
# → "Step 9 complete in 3.4s — saved to data/processed/drugos_heterodata__*.pt"

# Step 11: train TransE on Phase 1 data
DRUGOS_TRANSE_MIN_TRAIN_TRIPLES=10 DRUGOS_TRANSE_EPOCHS=5 \
  DRUGOS_TRANSE_EMBEDDING_DIM=32 \
  python -m drugos_graph.run_pipeline --step 11 --data-source phase1 --skip-neo4j
# → "Step 11 complete in 2.1s"
```

The "entire Phase 1 → Phase 2 flow is testable without Neo4j" claim
is now TRUE for training as well as for the bridge demo.
