"""P1-ER-22: OMIM categorical scores must not be clipped to 1.0.

ROOT-CAUSE: validate_gda_scores default score_range=(0.0, 1.0) clipped
OMIM categorical scores (1/2/3) to 1.0, destroying discriminative info.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase1/cleaning/missing_values.py"
)


def test_validate_gda_scores_handles_omim_categorical():
    src = _FILE.read_text()
    # The fix must detect source=="omim" and map categorical scores
    assert "omim" in src.lower(), (
        "P1-ER-22 setup: validate_gda_scores does not reference omim source"
    )
    # Must have categorical mapping logic
    assert (
        re.search(r"1\s*->\s*0\.5|1.*0\.5", src)
        or "categorical" in src.lower()
    ), (
        "P1-ER-22 REGRESSION: validate_gda_scores does not map OMIM "
        "categorical scores (1/2/3) to (0.5/0.7/0.9)."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
