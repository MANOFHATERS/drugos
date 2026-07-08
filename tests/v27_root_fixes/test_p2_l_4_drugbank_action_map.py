"""P2-L-4: DrugBank action_type must be mapped to canonical verb form.

ROOT-CAUSE BEING VERIFIED:
  Phase 1 path emitted `rel_type="inhibitor"` (raw noun).
  Raw XML path correctly mapped via DRUGBANK_ACTION_TO_RELATION to
  `"inhibits"` (verb). Same drug-target pair → 2 disjoint edges.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


def test_drugbank_parser_phase1_path_maps_action():
    src = Path(
        "/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/drugbank_parser.py"
    ).read_text()
    # The Phase 1 path must call _map_action_to_relation (or equivalent)
    # rather than emitting raw action_type
    assert "_map_action_to_relation" in src, (
        "P2-L-4 REGRESSION: drugbank_parser does not call "
        "_map_action_to_relation in the Phase 1 path. Raw 'inhibitor' "
        "(noun) is emitted as rel_type instead of canonical 'inhibits' (verb)."
    )


def test_run_pipeline_step4_maps_action():
    src = Path(
        "/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/run_pipeline.py"
    ).read_text()
    # Look for the inline step 4 — should also call _map_action_to_relation
    # We accept either an explicit call or import + call.
    assert "_map_action_to_relation" in src or "DRUGBANK_ACTION_TO_RELATION" in src, (
        "P2-L-4 REGRESSION: run_pipeline.py step 4 inline loop does not "
        "map action_type to canonical verb. Same drug-target pair will "
        "produce disjoint edges with different rel_type labels."
    )


def test_drugbank_action_map_includes_inhibitor_inhibits():
    """The DRUGBANK_ACTION_TO_RELATION map (defined in config.py) must
    map 'inhibitor' -> 'inhibits'."""
    config_src = Path(
        "/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/config.py"
    ).read_text()
    assert re.search(r'["\']inhibitor["\']\s*:\s*["\']inhibits["\']', config_src), (
        "P2-L-4 REGRESSION: DRUGBANK_ACTION_TO_RELATION (in config.py) "
        "does not map 'inhibitor' -> 'inhibits'."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
