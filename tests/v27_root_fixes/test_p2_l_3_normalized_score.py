"""P2-L-3: loaders must emit normalized_score in [0,1] alongside raw score.

ROOT-CAUSE BEING VERIFIED:
  STITCH/STRING scores on 0-1000 scale, OpenTargets/DisGeNET on 0-1,
  ChEMBL pchembl on 0-14, DRKG as string label. All stored under
  props["score"]. RL ranker compares apples to oranges.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_LOADERS = [
    "stitch_loader.py",
    "string_loader.py",
    "opentargets_loader.py",
    "disgenet_loader.py",
    "omim_loader.py",
    "chembl_loader.py",
    "drkg_loader.py",
]


@pytest.mark.parametrize("loader", _LOADERS)
def test_loader_emits_normalized_score(loader):
    path = Path(f"/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/{loader}")
    src = path.read_text()
    assert "normalized_score" in src, (
        f"P2-L-3 REGRESSION: {loader} does not emit `normalized_score`. "
        f"Score scale chaos persists — RL ranker cannot aggregate across "
        f"sources."
    )


def test_kg_builder_whitelists_normalized_score():
    src = Path(
        "/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/kg_builder.py"
    ).read_text()
    # EDGE_PROPERTY_WHITELIST must include normalized_score
    assert "normalized_score" in src, (
        "P2-L-3 REGRESSION: kg_builder.EDGE_PROPERTY_WHITELIST does not "
        "include `normalized_score`. The property will be stripped during "
        "load."
    )


def test_stitch_divides_by_1000():
    src = Path(
        "/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/stitch_loader.py"
    ).read_text()
    # Look for division by 1000 (or equivalent)
    assert re.search(r"/\s*1000|/\s*1_000|\*\s*0\.001", src), (
        "P2-L-3 REGRESSION: stitch_loader does not divide by 1000 to "
        "compute normalized_score. STITCH combined_score is on 0-1000 scale."
    )


def test_string_divides_by_1000():
    src = Path(
        "/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/string_loader.py"
    ).read_text()
    assert re.search(r"/\s*1000|/\s*1_000|\*\s*0\.001", src), (
        "P2-L-3 REGRESSION: string_loader does not divide by 1000."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
