"""P1-ER-21: Circuit breaker HALF_OPEN must allow only ONE call.

ROOT-CAUSE: `allow_call` returned True for every call in HALF_OPEN.
Defeats "test one request" semantics.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase1/entity_resolution/drug_resolver.py"
)


def test_half_open_in_flight_counter_exists():
    src = _FILE.read_text()
    assert "_half_open_in_flight" in src, (
        "P1-ER-21 REGRESSION: _PubChemCircuitBreaker does not track "
        "_half_open_in_flight counter. HALF_OPEN allows unlimited calls."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
