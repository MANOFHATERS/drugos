"""P1-16: PubChem rate_limit_interval < 0.2 must raise, not warn.

ROOT-CAUSE: misconfigured env var only warned → worker IP banned from
PubChem for 24 hours.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase1/pipelines/pubchem_pipeline.py"
)


def test_pubchem_rate_limit_raises_not_warns():
    src = _FILE.read_text()
    # Find the rate_limit_interval < 0.2 check
    m = re.search(
        r"rate_limit_interval\s*<\s*0\.2.*?(?=\n    def\s|\nclass\s|\Z)",
        src,
        re.DOTALL,
    )
    assert m, "P1-16 setup: cannot find rate_limit_interval < 0.2 check"
    body = m.group(0)
    # Must raise, not warn
    assert "raise" in body, (
        "P1-16 REGRESSION: rate_limit_interval < 0.2 only warns. Misconfigured "
        "env var gets worker IP banned from PubChem for 24 hours."
    )
    assert "PubChemPipelineError" in src, (
        "P1-16 setup: PubChemPipelineError class not found"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
