"""P2-L-5: STITCH stereochemistry mapping must NOT be inverted.

ROOT-CAUSE BEING VERIFIED:
  Per STITCH docs: CIDm = merged stereoisomers (FLAT/non-stereo),
  CIDs = stereo-specific separate form. The code had it inverted.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path("/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/stitch_loader.py")


def test_stitch_stereo_mapping_not_inverted():
    src = _FILE.read_text()
    # Find the mapping dict
    match = re.search(
        r'"\w+"\s*:\s*"stereo_specific"[\s,]*"\w+"\s*:\s*"non_stereo"|'
        r'"\w+"\s*:\s*"non_stereo"[\s,]*"\w+"\s*:\s*"stereo_specific"',
        src,
    )
    assert match, "P2-L-5 setup: cannot find stereo mapping dict"
    mapping_str = match.group(0)

    # Per STITCH docs: m = merged = FLAT/non_stereo, s = separate/stereo_specific
    assert '"m": "non_stereo"' in mapping_str, (
        "P2-L-5 REGRESSION: CIDm is mapped to 'stereo_specific' but should be "
        "'non_stereo' (CIDm = merged stereoisomers = FLAT form per STITCH docs)."
    )
    assert '"s": "stereo_specific"' in mapping_str, (
        "P2-L-5 REGRESSION: CIDs is mapped to 'non_stereo' but should be "
        "'stereo_specific' (CIDs = stereo-specific separate form per STITCH docs)."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
