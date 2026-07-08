"""TOP-11: DATABASE_URL silent cosmic:cosmic swap must require opt-in.

ROOT-CAUSE: silent insecure default in dev mode. Operators don't know
they're using default credentials.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase1/config/settings.py"
)


def test_dev_default_db_requires_opt_in():
    src = _FILE.read_text()
    # The fix must require DRUGOS_DEV_ALLOW_DEFAULT_DB=1 env var
    assert "DRUGOS_DEV_ALLOW_DEFAULT_DB" in src, (
        "TOP-11 REGRESSION: settings.py silently swaps DATABASE_URL to "
        "cosmic:cosmic in dev mode without opt-in. Operators don't know "
        "they're using default credentials."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
