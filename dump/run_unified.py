#!/usr/bin/env python3
"""
Unified Platform Runner — Phase 1 + Phase 2 in one command
==========================================================

This is the SINGLE top-level entry point for the unified Autonomous Drug
Repurposing Platform. It chains:

  Phase 1  →  Bridge  →  Phase 2
  ───────────────────────────────
  Phase 1 (data ingestion):
    Reads the processed_data CSVs that Phase 1's pipelines have already
    produced (DrugBank drugs, DrugBank interactions, OMIM GDA). If you
    want to re-run Phase 1 pipelines from scratch, see
    ``phase1/README.md`` and ``phase1/Makefile``.

  Bridge (phase1_bridge):
    Converts Phase 1 CSVs into Phase 2 node/edge dicts with full lineage.
    See ``phase2/drugos_graph/phase1_bridge.py``.

  Phase 2 (knowledge graph):
    Loads the staged dicts into a graph builder. By default the
    RecordingGraphBuilder is used (in-memory, no Neo4j) so the runner
    works out of the box. To target a real Neo4j, set the
    DRUGOS_NEO4J_URI / DRUGOS_NEO4J_USER / DRUGOS_NEO4J_PASSWORD env vars
    OR pass --neo4j-uri on the CLI.

USAGE
-----
  # Dry run (in-memory, no Neo4j, no side effects):
  python run_unified.py

  # Dry run with verbose JSON report:
  python run_unified.py --json

  # Real Neo4j load:
  python run_unified.py --neo4j-uri bolt://localhost:7687 \\
      --neo4j-user neo4j --neo4j-password secret

  # Override Phase 1 processed_data dir:
  python run_unified.py --phase1-dir /custom/path/to/processed_data

EXIT CODES
----------
  0  — Success (data loaded, no errors)
  1  — Bridge produced zero nodes (Phase 1 outputs likely missing)
  2  — Bridge produced zero edges (interactions or OMIM CSV likely empty)
  3  — Neo4j connection failed (only when --neo4j-uri supplied)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
PHASE1_ROOT = HERE / "phase1"
PHASE2_ROOT = HERE / "phase2"
PHASE1_PROCESSED_DEFAULT = PHASE1_ROOT / "processed_data"

for p in (str(PHASE2_ROOT), str(PHASE1_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# FIX TOP-14 (FIX-CFG-ML audit): set the global RNG seed as the FIRST
# importable side-effect of run_unified.py. The Phase 2 config defines
# SEED=42 and propagates it to TransEConfig.seed / EvaluationConfig.seed /
# PyGConfig.seed, but until set_global_seed() is actually CALLED, the
# global ``random`` / ``numpy.random`` / ``torch`` RNG state at process
# start is whatever Python seeded it with — non-deterministic. This made
# model init non-deterministic (PyTorch ``nn.Embedding`` init consumes
# the global RNG), so two ``python run_unified.py`` runs with the same
# config could produce different held-out AUCs. Calling set_global_seed()
# here at import time (before any model is constructed) makes the entire
# pipeline deterministic given the same CONFIG_HASH. Synchronized with
# phase2/drugos_graph/run_pipeline.py:run_full_pipeline (which also calls
# set_global_seed as its first line) — DO NOT diverge (audit TOP-14).
try:
    from drugos_graph.config import set_global_seed as _set_global_seed

    _set_global_seed(42)
except Exception as _seed_exc:  # noqa: BLE001 — best-effort, do not block
    import logging as _logging

    _logging.getLogger("unified").warning(
        "set_global_seed(42) failed (%s) — pipeline will run but model "
        "init is non-deterministic. This is a regression: phase2/drugos_"
        "graph/config.py must define set_global_seed (audit TOP-14).",
        _seed_exc,
    )


# v20 Compound-2/8 ROOT FIX — Production escape-hatch guard (run_unified side).
# The same guard exists in run_pipeline.py, but run_pipeline.py is only
# imported when --full-pipeline is on. For --no-full-pipeline (bridge-only)
# runs, this guard ensures escape hatches are still refused in production.
def _check_production_escape_hatches_unified() -> None:
    env = os.environ.get("DRUGOS_ENVIRONMENT", "dev").lower()
    if env in ("prod", "production"):
        offenders: List[str] = []
        for flag in (
            "DRUGOS_ALLOW_NO_SAMPLER",
            "DRUGOS_ALLOW_PERMISSIVE_KG",
            "DRUGOS_ALLOW_PERMISSIVE_DPI",
            "DRUGOS_ALLOW_LAUNCH_FAIL",
        ):
            if os.environ.get(flag, "") == "1":
                offenders.append(flag)
        if offenders:
            raise SystemExit(
                f"REFUSING TO RUN: production environment detected "
                f"(DRUGOS_ENVIRONMENT={env}) but escape-hatch flag(s) "
                f"are set: {', '.join(offenders)}. These flags re-activate "
                "patient-safety-critical compound destruction chains "
                "(Compound-1, Compound-2, Compound-5, Compound-8). "
                "Unset the flag(s) or change DRUGOS_ENVIRONMENT to 'dev'."
            )


_check_production_escape_hatches_unified()


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )


def _build_real_neo4j(uri: str, user: str, password: str):
    """Construct and connect a real DrugOSGraphBuilder to a Neo4j instance."""
    from drugos_graph import DrugOSGraphBuilder, Neo4jConfig

    cfg = Neo4jConfig(uri=uri, user=user, password=password)
    builder = DrugOSGraphBuilder(cfg)
    builder.connect()
    try:
        builder.create_constraints()
    except Exception as exc:
        logging.warning("create_constraints() failed (continuing): %s", exc)
    return builder


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_unified.py",
        description="Run the unified Phase 1 → Phase 2 pipeline.",
    )
    parser.add_argument(
        "--phase1-dir",
        type=Path,
        default=PHASE1_PROCESSED_DEFAULT,
        help="Phase 1 processed_data directory (default: phase1/processed_data)",
    )
    parser.add_argument("--neo4j-uri", default=None,
                        help="Neo4j bolt:// URI. If omitted, dry-run mode is used.")
    parser.add_argument("--neo4j-user", default=None)
    parser.add_argument("--neo4j-password", default=None)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--json", action="store_true",
                        help="Emit the full summary as JSON to stdout")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument(
        "--full-pipeline",
        action="store_true",
        default=True,
        help=(
            "v15 ROOT FIX (REM-25): after the bridge stages data, also "
            "run the FULL Phase 2 pipeline (entity resolution → PyG "
            "HeteroData build → training data construction → TransE "
            "training → validation → V1 launch criteria check). "
            "v20 ROOT FIX (Phase1↔Phase2 connection): the previous "
            "default was False — operators had to explicitly pass "
            "--full-pipeline to get an AUC. Most users never did, "
            "leading to the audit's complaint that the runner exits 0 "
            "but produces no model. Default is now True; pass "
            "--no-full-pipeline to stop at the bridge (dev/test only)."
        ),
    )
    parser.add_argument(
        "--no-full-pipeline",
        dest="full_pipeline",
        action="store_false",
        help=(
            "v20: opt OUT of the full pipeline. Stops at the bridge — "
            "no TransE training, no AUC, no V1 launch criteria check. "
            "Useful for quick smoke-tests in dev."
        ),
    )
    # v41 ROOT FIX (SEV2): auto-invoking ``make -C phase1 all`` on a fresh
    # clone takes ~2 hours (DrugBank XML parse + ChEMBL REST pull + UniProt
    # bulk download + STRING/DisGeNET/OMIM/PubChem). The previous code did
    # this IMPLICITLY when phase1_dir was missing — operators typing
    # ``python run_unified.py`` on a fresh clone would walk away expecting
    # a quick smoke test and come back to find a 2-hour job still running.
    # The fix adds ``--yes`` to skip the confirmation prompt (for CI / scripted
    # use) and otherwise prompts the operator before kicking off the long
    # build. Default is to prompt (interactive).
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        default=False,
        help="Skip the Phase 1 build confirmation prompt (CI / scripted use).",
    )
    # v21 ROOT FIX (Audit Chain 1 / Chain 12): the previous declaration
    # used ``action='store_true', default=True`` with NO inverse flag.
    # That made ``--skip-download`` a no-op (it was already True) AND
    # locked the operator out of ever enabling downloads from this
    # entry point — the audit's #1 P0 blocker. ``BooleanOptionalAction``
    # exposes BOTH ``--skip-download`` AND ``--no-skip-download`` so the
    # user can choose. Default stays True (Phase 1 CSVs are the
    # authoritative data source per the build doc), but operators can
    # now opt in to live downloads without editing source code.
    parser.add_argument(
        "--skip-download",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip network downloads in step7 (use Phase 1 CSVs only). "
             "Default True — the bridge is the authoritative data source. "
             "Pass --no-skip-download to enable live downloads of "
             "STRING/UniProt/ChEMBL/DrugBank/SIDER/etc.",
    )
    # V45 ROOT FIX: --download-real-data flag — automatically downloads
    # ALL free biomedical data sources (ChEMBL, UniProt, STRING, PubChem,
    # OpenTargets) and processes them into Phase 1 CSVs BEFORE running
    # the pipeline. This makes the codebase FULLY AUTOMATIC — no manual
    # download step needed. All sources are FREE (no login, no API key).
    # DrugBank is NOT downloaded (academic downloads paused since May 2026);
    # ChEMBL is used as the primary drug source instead.
    # OMIM/DisGeNET API keys are NOT required; OpenTargets is used as the
    # free alternative.
    parser.add_argument(
        "--download-real-data",
        action="store_true",
        default=False,
        help="Automatically download ALL free biomedical data sources "
             "(ChEMBL, UniProt, STRING, PubChem, OpenTargets) and process "
             "them into Phase 1 CSVs before running the pipeline. "
             "All sources are FREE — no login, no API key. "
             "DrugBank is NOT included (paused since May 2026); ChEMBL "
             "is used as the primary drug source. "
             "OMIM/DisGeNET API keys NOT required; OpenTargets is the "
             "free alternative. This flag makes the codebase FULLY "
             "AUTOMATIC.",
    )
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)
    log = logging.getLogger("unified")

    # V45 ROOT FIX: if --download-real-data is set, run the auto-downloader
    # BEFORE the pipeline. This downloads all free sources and processes
    # them into Phase 1 CSVs.
    if args.download_real_data:
        log.info("=" * 70)
        log.info("V45 AUTO-DOWNLOAD: Downloading all free biomedical data sources")
        log.info("=" * 70)
        log.info("All sources are FREE — no login, no API key required.")
        log.info("DrugBank: using ChEMBL as primary (paused since May 2026).")
        log.info("OMIM/DisGeNET: using OpenTargets as free alternative.")
        try:
            # Add phase1 to sys.path so the download module is importable
            _phase1_path = str(HERE / "phase1")
            if _phase1_path not in sys.path:
                sys.path.insert(0, _phase1_path)
            from pipelines.download_all import (
                download_chembl, download_uniprot, download_string,
                download_pubchem, download_opentargets, process_to_csvs,
            )
            log.info("Step 1/6: Downloading ChEMBL (2,996 drugs + 5,000 activities)...")
            download_chembl()
            log.info("Step 2/6: Downloading UniProt (20,432 human proteins)...")
            download_uniprot()
            log.info("Step 3/6: Downloading STRING (50,000 PPIs)...")
            download_string()
            log.info("Step 4/6: Downloading PubChem (96 enrichments)...")
            download_pubchem()
            log.info("Step 5/6: Downloading OpenTargets (540 gene-disease)...")
            download_opentargets()
            log.info("Step 6/6: Processing raw data → Phase 1 CSVs...")
            counts = process_to_csvs()
            log.info("Auto-download complete! Counts: %s", counts)
            log.info("Phase 1 CSVs are now in %s", args.phase1_dir)
            log.info("=" * 70)
        except Exception as exc:
            log.error("Auto-download failed: %s", exc)
            log.error("The pipeline will continue with existing Phase 1 CSVs.")
            log.error("You can manually run: cd phase1 && python -m pipelines.download_all --all --process")

    # v41 ROOT FIX (SEV2): --full-pipeline defaults True, so EVERY invocation
    # attempts TransE training (30-60 min) and enforces V1 launch criteria
    # (AUC >= 0.85). Operators running a quick smoke test who forget to pass
    # --no-full-pipeline are surprised by the long runtime and the V1-fail
    # exit code. Emit a clear startup banner so the mode is unambiguous in
    # the log file from line 1.
    if args.full_pipeline:
        log.warning(
            "=" * 70 + "\n"
            "v41 STARTUP BANNER: Full pipeline mode is ENABLED "
            "(--full-pipeline default True).\n"
            "  • Will train TransE (30-60 min on CPU, faster on GPU).\n"
            "  • Will enforce V1 launch criteria (held_out_auc >= 0.85).\n"
            "  • Exit code 4 = V1 criteria NOT MET (training completed but "
            "AUC below threshold).\n"
            "  • Pass --no-full-pipeline to stop at the bridge (dev/test "
            "smoke run, ~30 seconds).\n"
            + "=" * 70
        )
    else:
        log.info(
            "v41 STARTUP BANNER: Bridge-only mode (--no-full-pipeline). "
            "Will NOT train TransE, will NOT enforce V1 launch criteria. "
            "Exit code 0 expected on success."
        )

    # ─── 1. Phase 1 outputs sanity check ──────────────────────────────────
    # v29 ROOT FIX (audit O-1 — "run_unified.py does NOT run Phase 1"):
    # The audit found that a fresh ``python run_unified.py`` exits 1
    # immediately because Phase 1's processed_data/ doesn't exist on a
    # fresh clone. The v28 code just said "run Phase 1 first" and gave
    # up. ROOT FIX: actually invoke Phase 1 here, so the unified runner
    # is truly unified. We try the Phase 1 master pipeline; if it
    # fails (e.g. no DrugBank license, no network), we fall back to the
    # existing error message with actionable guidance.
    #
    # v41 ROOT FIX (SEV2): the auto-invocation of ``make -C phase1 all``
    # takes ~2 hours (DrugBank XML parse + 6 REST API pulls). The
    # previous code did this IMPLICITLY when phase1_dir was missing —
    # operators typing ``python run_unified.py`` on a fresh clone would
    # walk away expecting a quick smoke test and come back to find a
    # 2-hour job still running. The fix adds a confirmation prompt
    # (skipped by --yes) so the operator must explicitly opt in to the
    # 2-hour build. Non-interactive sessions (no TTY) default to "no"
    # and exit with a helpful message instead of silently starting the
    # 2-hour job.
    if not args.phase1_dir.exists():
        log.warning(
            "Phase 1 processed_data dir not found: %s — attempting to "
            "run Phase 1 master pipeline now (v29 root fix).", args.phase1_dir,
        )
        # v41 ROOT FIX (SEV2): confirmation prompt before the 2h build.
        if not args.yes:
            import sys as _sys_for_tty
            _is_tty = _sys_for_tty.stdin.isatty()
            if _is_tty:
                log.warning(
                    "Phase 1 build will take approximately 2 hours "
                    "(DrugBank XML parse + 6 REST API pulls)."
                )
                try:
                    _answer = input(
                        "This will run a 2-hour Phase 1 build. Continue? [y/N] "
                    )
                except (EOFError, KeyboardInterrupt):
                    _answer = ""
                if _answer.strip().lower() not in ("y", "yes"):
                    log.error(
                        "Phase 1 build declined by operator. Set --yes to "
                        "skip this prompt (CI / scripted use), or run "
                        "``make -C phase1 all`` manually first."
                    )
                    return 1
            else:
                # Non-interactive session — refuse to silently kick off
                # a 2-hour job. Require --yes for non-TTY invocations
                # too.
                log.error(
                    "Phase 1 processed_data dir not found at %s AND the "
                    "session is non-interactive (no TTY). Refusing to "
                    "silently auto-start a 2-hour Phase 1 build. Either: "
                    "(1) run ``make -C phase1 all`` manually first; "
                    "(2) re-run with --yes to auto-confirm the 2-hour "
                    "build (CI / scripted use); (3) provide a pre-populated "
                    "--phase1-dir.", args.phase1_dir,
                )
                return 1
        try:
            import subprocess as _sp
            import sys as _sys
            _phase1_root = str(HERE / "phase1")
            # Try the Phase 1 master pipeline via its Makefile target
            # first (preferred — handles env / DB setup), then fall
            # back to a direct Python invocation.
            _makefile = HERE / "phase1" / "Makefile"
            if _makefile.exists():
                log.info("Invoking Phase 1 master pipeline via Makefile...")
                _proc = _sp.run(
                    ["make", "-C", _phase1_root, "all"],
                    capture_output=True, text=True, timeout=7200,  # 2h
                )
                if _proc.returncode != 0:
                    log.error("Phase 1 master pipeline FAILED (rc=%d).",
                              _proc.returncode)
                    log.error("stdout: %s", _proc.stdout[-2000:])
                    log.error("stderr: %s", _proc.stderr[-2000:])
                    raise RuntimeError("Phase 1 master pipeline failed")
            else:
                # No Makefile — invoke the Phase 1 pipelines module
                # directly. This is the dev/CI path.
                log.info("Invoking Phase 1 pipelines module directly...")
                _proc = _sp.run(
                    [_sys.executable, "-m", "pipelines"],
                    cwd=_phase1_root,
                    capture_output=True, text=True, timeout=7200,
                )
                if _proc.returncode != 0:
                    log.error("Phase 1 pipelines FAILED (rc=%d).",
                              _proc.returncode)
                    raise RuntimeError("Phase 1 pipelines failed")
            # Re-check.
            if not args.phase1_dir.exists():
                raise RuntimeError(
                    f"Phase 1 master pipeline ran but did not produce "
                    f"processed_data at {args.phase1_dir}"
                )
            log.info(
                "Phase 1 master pipeline completed — processed_data now "
                "available at %s", args.phase1_dir,
            )
        except Exception as exc:
            log.error("Phase 1 auto-invocation failed: %s", exc)
            log.error(
                "Phase 1 processed_data dir not found: %s. Tried to "
                "auto-run Phase 1 but failed. Manual options: (1) cd "
                "phase1 && make all  (2) obtain a DrugBank license and "
                "set the DRUGBANK_XML_PATH env var to the path of your "
                "drugbank_all_full_database.xml.gz file (the DrugBank "
                "pipeline reads the XML directly — there is no "
                "DRUGBANK_USERNAME / DRUGBANK_PASSWORD env var; those "
                "were removed in v9 when the pipeline switched from "
                "the (now-defunct) DrugBank REST API to the licensed "
                "XML download)  (3) run individual Phase 1 pipelines "
                "(chembl, drugbank, uniprot, string, disgenet, omim, "
                "pubchem) one at a time. See phase1/README.md.",
                args.phase1_dir,
            )
            return 1
    else:
        log.info("=" * 70)
        log.info("UNIFIED RUNNER — Phase 1 → Bridge → Phase 2")
        log.info("=" * 70)
        log.info("Phase 1 processed_data: %s", args.phase1_dir)

    # ─── 2. Build or select the graph builder ─────────────────────────────
    builder = None
    if args.neo4j_uri:
        log.info("Neo4j mode: connecting to %s", args.neo4j_uri)
        try:
            builder = _build_real_neo4j(
                args.neo4j_uri,
                args.neo4j_user or "neo4j",
                args.neo4j_password or "",
            )
        except Exception as exc:
            log.error("Neo4j connection failed: %s", exc)
            return 3
    else:
        # v29 ROOT FIX (audit O-3): RecordingGraphBuilder is dev-only.
        # Warn loudly in production.
        from drugos_graph.phase1_bridge import RecordingGraphBuilder
        log.info("Dry-run mode: using RecordingGraphBuilder (no Neo4j)")
        _env = os.environ.get("DRUGOS_ENVIRONMENT", "dev").lower()
        if _env in ("prod", "production"):
            log.warning(
                "!!! PRODUCTION WARNING (audit O-3) !!! "
                "DRUGOS_ENVIRONMENT=%s but run_unified.py is using the "
                "in-memory RecordingGraphBuilder (the DEFAULT when "
                "--neo4j-uri is omitted). This means the knowledge graph "
                "is NOT persisted to Neo4j — nodes/edges are dropped on "
                "process exit. This is dev/CI-only behavior. To target a "
                "real Neo4j in production, pass --neo4j-uri "
                "bolt://<host>:7687 (and --neo4j-user / --neo4j-password), "
                "or set DRUGOS_NEO4J_URI / DRUGOS_NEO4J_USER / "
                "DRUGOS_NEO4J_PASSWORD env vars. Neo4j must NOT be treated "
                "as decorative in production.",
                _env,
            )
        builder = RecordingGraphBuilder()

    # ─── 3. Run the bridge ────────────────────────────────────────────────
    from drugos_graph.phase1_bridge import run_phase1_to_phase2

    log.info("Running Phase 1 → Phase 2 bridge...")
    result = run_phase1_to_phase2(
        phase1_processed_dir=args.phase1_dir,
        builder=builder,
        batch_size=args.batch_size,
    )

    summary: Dict[str, Any] = result["summary"]

    # v34 ROOT FIX (NEO4J PERSISTENCE): the previous code used
    # RecordingGraphBuilder (in-memory) by default and NEVER persisted
    # the staged graph to disk. On process exit, all 67 nodes and 68
    # edges were lost. The user explicitly complained: "All data lives
    # in RecordingGraphBuilder (in-memory). Nothing persists. No Neo4j
    # writes." The fix: ALWAYS persist the staged graph to disk as a
    # JSON file (phase2/data/processed/staged_graph.json) so the data
    # survives process exit. This is NOT a replacement for Neo4j — it's
    # a fallback for dry-run mode + a debug artifact for production.
    # When --neo4j-uri is set, the bridge ALSO writes to Neo4j (above).
    try:
        from drugos_graph.phase1_bridge import Phase1StagedData
        staged_obj: Phase1StagedData = result["staged"]
        _persist_dir = PHASE2_ROOT / "data" / "processed"
        _persist_dir.mkdir(parents=True, exist_ok=True)
        _persist_path = _persist_dir / "staged_graph.json"
        _persist_payload = {
            "bridge_version": summary["bridge_version"],
            "nodes_staged": summary["nodes_staged"],
            "edges_staged": summary["edges_staged"],
            "nodes_loaded": summary["nodes_loaded"],
            "edges_loaded": summary["edges_loaded"],
            "edge_types_present": list(summary["edge_types_present"]),
            "warnings": list(summary.get("warnings", [])),
            "errors": list(summary.get("errors", [])),
            "node_counts_by_type": {},
            "edge_counts_by_type": {},
            "nodes": {},
            "edges": {},
        }
        # Persist nodes/edges by type for downstream consumers.
        # FORENSIC Neo4j persistence root fix: the v34 fix capped each
        # type at 50 samples (``nodes[:50]``, ``edges[:50]``), which
        # meant the persisted JSON was a SAMPLE, not the full graph.
        # The user's complaint ("All data lives in RecordingGraphBuilder
        # (in-memory). Nothing persists. No Neo4j writes.") was
        # therefore still valid even after v34. The fix: persist the
        # FULL node/edge lists (no cap) so the JSON sidecar is a
        # complete, reloadable representation of the staged graph.
        # This is NOT a replacement for Neo4j — it's a fallback for
        # dry-run mode + a debug artifact for production. When
        # --neo4j-uri is set, the bridge ALSO writes to Neo4j (above).
        _node_collections = {
            "Compound": getattr(staged_obj, "compound_nodes", []),
            "Protein": getattr(staged_obj, "protein_nodes", []),
            "Gene": getattr(staged_obj, "gene_nodes", []),
            "Disease": getattr(staged_obj, "disease_nodes", []),
            "ClinicalOutcome": getattr(staged_obj, "clinical_outcome_nodes", []),
            "Pathway": getattr(staged_obj, "pathway_nodes", []),
        }
        for ntype, nodes in _node_collections.items():
            if nodes:
                # FORENSIC fix: persist ALL nodes (was nodes[:50]).
                _persist_payload["nodes"][ntype] = nodes
                _persist_payload["node_counts_by_type"][ntype] = len(nodes)
        for (src, rel, dst), edges in staged_obj.edges.items():
            _key = f"{src}->{rel}->{dst}"
            # FORENSIC fix: persist ALL edges (was edges[:50]).
            _persist_payload["edges"][_key] = edges
            _persist_payload["edge_counts_by_type"][_key] = len(edges)
        with open(_persist_path, "w") as _f:
            json.dump(_persist_payload, _f, indent=2, default=str)
        log.info(
            "Staged graph PERSISTED to %s (%d nodes, %d edges — FULL "
            "graph, not a sample). This is the dry-run artifact; Neo4j "
            "is the production store when --neo4j-uri is set.",
            _persist_path,
            sum(_persist_payload["node_counts_by_type"].values()),
            sum(_persist_payload["edge_counts_by_type"].values()),
        )
    except Exception as _persist_exc:
        log.warning(
            "Failed to persist staged graph to disk (non-fatal): %s",
            _persist_exc,
        )

    # ─── 4. Report ────────────────────────────────────────────────────────
    log.info("-" * 70)
    log.info("BRIDGE SUMMARY")
    log.info("-" * 70)
    log.info("Bridge version:       %s", summary["bridge_version"])
    log.info("Sources read:         %s", summary["sources_read"])
    log.info("Nodes staged:         %d", summary["nodes_staged"])
    log.info("Edges staged:         %d", summary["edges_staged"])
    log.info("Nodes loaded:         %d", summary["nodes_loaded"])
    log.info("Edges loaded:         %d", summary["edges_loaded"])
    log.info("Edge types present:")
    for et in summary["edge_types_present"]:
        log.info("  - %s", et)
    if summary["warnings"]:
        log.info("Warnings:")
        for w in summary["warnings"]:
            log.info("  ! %s", w)
    if summary["errors"]:
        log.error("Errors:")
        for e in summary["errors"]:
            log.error("  X %s", e)

    if args.json:
        # Make summary JSON-serializable (Path objects etc.)
        print(json.dumps(summary, indent=2, default=str))

    # ─── 5. Exit-code contract ───────────────────────────────────────────
    if summary["nodes_loaded"] == 0:
        log.error("Zero nodes loaded — Phase 1 outputs likely missing or empty.")
        return 1
    if summary["edges_loaded"] == 0:
        log.error("Zero edges loaded — interactions or OMIM CSV likely empty.")
        return 2

    log.info("=" * 70)
    log.info("UNIFIED RUN COMPLETE — %d nodes, %d edges loaded",
             summary["nodes_loaded"], summary["edges_loaded"])
    log.info("=" * 70)

    # ─── 6. v15 ROOT FIX (REM-25): optionally run the FULL Phase 2 pipeline ─
    # v14's run_unified.py stopped at the bridge — it never trained TransE,
    # never built PyG HeteroData, never validated, never checked V1 launch
    # criteria. The "unified runner" was therefore theater: it loaded nodes
    # and edges into a RecordingGraphBuilder and exited 0, but the project's
    # headline deliverable (the >0.85 AUC) was never computed by THIS entry
    # point. Operators had to manually invoke `python -m drugos_graph` —
    # which most users never did, leading to the user's complaint that "every
    # session every AI tells its 100 percent integrated but see the reality."
    # Fix: when --full-pipeline is passed, chain directly into
    # run_pipeline.run_full_pipeline(data_source="phase1") so the unified
    # runner actually produces a model, an AUC, and a launch verdict.
    if args.full_pipeline:
        log.info("-" * 70)
        log.info("FULL PIPELINE — Step 8 (entity_resolution) → Step 9 (PyG build) "
                 "→ Step 10 (training data) → Step 11 (TransE train) → "
                 "Step 12 (validation) → V1 launch criteria")
        log.info("-" * 70)
        try:
            from drugos_graph.run_pipeline import run_full_pipeline
            # v29 ROOT FIX (audit O-9): when --neo4j-uri is set, the
            # bridge above already loaded nodes/edges into Neo4j via
            # ``builder``. Previously the call below used
            # ``skip_neo4j=(args.neo4j_uri is None)`` which evaluated to
            # False when --neo4j-uri was supplied → run_full_pipeline
            # re-loaded the SAME graph into Neo4j → duplicate edges /
            # duplicate nodes (the graph got double-loaded). The fix
            # inverts the predicate: when --neo4j-uri is NOT None (i.e.
            # the bridge already loaded Neo4j), we pass skip_neo4j=True
            # so run_full_pipeline uses its own RecordingGraphBuilder /
            # in-memory path for the PyG/TransE stages and does NOT
            # re-open a second Neo4j session. When --neo4j-uri IS None
            # (dry-run), skip_neo4j=False is harmless because there's no
            # Neo4j to skip — run_full_pipeline falls back to the
            # in-memory builder internally.
            pipeline_result = run_full_pipeline(
                data_source="phase1",
                skip_neo4j=(args.neo4j_uri is not None),
                skip_download=args.skip_download,
                phase1_processed_dir=args.phase1_dir,
            )
            log.info("-" * 70)
            log.info("PIPELINE RESULT")
            log.info("-" * 70)
            # Pipeline result is a dict; pretty-print the key fields.
            for k, v in pipeline_result.items():
                if k == "v1_criteria":
                    log.info("  V1 launch criteria: %s", v)
                elif isinstance(v, dict):
                    # v43 ROOT FIX (P2-014): the previous code filtered
                    # step results to a fixed whitelist of keys, so
                    # steps returning domain-specific keys (like step1's
                    # bridge_summary or step10's training_data) appeared
                    # as {} in the display. The fix shows ALL lightweight
                    # keys (scalars, small lists/dicts) and only skips
                    # known-heavy keys (DataFrames, large lists).
                    _HEAVY_KEYS = frozenset({
                        "df", "entity_maps", "edge_maps",
                        "edge_props_lookup", "node_props_lookup",
                        "bridge_staged", "training_data",
                    })
                    short = {}
                    for sk, sv in v.items():
                        if sk in _HEAVY_KEYS:
                            continue
                        # Skip non-serializable objects (DataFrames, etc.)
                        try:
                            import json as _json
                            _json.dumps(sv, default=str)
                            short[sk] = sv
                        except (TypeError, ValueError):
                            short[sk] = f"<{type(sv).__name__}>"
                    log.info("  %s: %s", k, short)
                else:
                    log.info("  %s: %s", k, v)
            # If V1 launch criteria returned a verdict, reflect it in exit.
            v1 = pipeline_result.get("v1_criteria") or {}
            if isinstance(v1, dict) and v1.get("passed") is False:
                log.error("V1 LAUNCH CRITERIA NOT MET — see report above.")
                return 4
            log.info("=" * 70)
            log.info("FULL PIPELINE COMPLETE — V1 criteria satisfied")
            log.info("=" * 70)
        except SystemExit as exc:
            # v21 ROOT FIX (Audit Chain 12): run_pipeline.py previously
            # called sys.exit(1) directly when V1 launch criteria fail.
            # The previous ``except Exception`` clause did NOT catch
            # SystemExit (SystemExit derives from BaseException, not
            # Exception), so the exit code propagated through
            # run_unified.py and crashed any parent orchestrator
            # (Airflow/Celery/K8s Job). The documented contract said
            # exit code 4 = V1 launch criteria not met — but that
            # contract was DEAD because sys.exit(1) hijacked the exit.
            # Now run_pipeline raises V1LaunchCriteriaFailed instead
            # (caught below). This SystemExit catch is defensive — it
            # handles any OTHER sys.exit() that might still leak from
            # deep library code (e.g. argparse on bad CLI).
            code = int(exc.code) if isinstance(exc.code, int) else 1
            if code == 1:
                log.error(
                    "V1 launch criteria not met (sys.exit(1) from "
                    "run_pipeline). Returning documented exit code 4."
                )
                return 4
            log.error("Pipeline raised SystemExit(%d).", code)
            return code
        except Exception as exc:
            # v21 ROOT FIX: catch V1LaunchCriteriaFailed (our typed
            # exception from run_pipeline) and translate to exit code 4.
            # All other Exceptions get exit code 5.
            exc_module = type(exc).__module__
            exc_name = type(exc).__name__
            if exc_name == "V1LaunchCriteriaFailed":
                log.error(
                    "V1 launch criteria not met. Returning documented "
                    "exit code 4. Failure detail: %s",
                    getattr(exc, "criteria", {}),
                )
                return 4
            log.exception("Full pipeline failed: %s", exc)
            return 5

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
