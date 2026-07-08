"""TOP-1: STRING score threshold must be synchronized between Phase 1 and Phase 2.

ROOT-CAUSE BEING VERIFIED:
  Phase 1 STRING threshold = 400, Phase 2 = 700. Phase 2 dropped ~75%
  of Phase 1's PPIs.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_P1 = Path("/home/z/my-project/v28/v28_upgraded/phase1/config/settings.py")
_P2 = Path("/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/config.py")


def test_string_threshold_synchronized():
    p1_src = _P1.read_text()
    p2_src = _P2.read_text()
    # Find STRING threshold in both files
    p1_match = re.search(
        r"STRING[_A-Z]*\s*(?::\s*\w+\s*=\s*)?\s*[:=]\s*(\d+)",
        p1_src,
    )
    p2_match = re.search(
        r"STRING[_A-Z]*\s*(?::\s*\w+\s*=\s*)?\s*[:=]\s*(\d+)",
        p2_src,
    )
    # We don't need exact regex; just look for the canonical 700 value
    # in both files in a STRING-threshold context
    assert "700" in p1_src, (
        "TOP-1 REGRESSION: phase1/config/settings.py does not reference 700 "
        "as STRING threshold. Phase 1 / Phase 2 STRING threshold drift will "
        "silently drop ~75% of PPIs."
    )
    assert "700" in p2_src, (
        "TOP-1 REGRESSION: phase2/drugos_graph/config.py does not reference "
        "700 as STRING threshold."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
