"""TOP-3: RESULTS_PERSIST_PATH must be defined, not silently skipped.

ROOT-CAUSE BEING VERIFIED:
  __main__.py referenced RESULTS_PERSIST_PATH which was never defined.
  Broad except silently swallowed. V1 launch check skipped.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path("/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/config.py")
_MAIN = Path("/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/__main__.py")


def test_results_persist_path_defined_in_config():
    src = _FILE.read_text()
    assert "RESULTS_PERSIST_PATH" in src, (
        "TOP-3 REGRESSION: config.py does not define RESULTS_PERSIST_PATH. "
        "__main__.py references it but the broad except silently swallowed "
        "the NameError, skipping the V1 launch check."
    )


def test_main_does_not_use_bare_except():
    src = _MAIN.read_text()
    # Find any `except Exception:` near RESULTS_PERSIST_PATH usage
    # The fix should narrow it to (ImportError, AttributeError)
    # Look for the narrowed except pattern
    assert re.search(r"except\s*\(\s*ImportError\s*,\s*AttributeError\s*\)", src), (
        "TOP-3 REGRESSION: __main__.py does not narrow the broad except "
        "around RESULTS_PERSIST_PATH usage to (ImportError, AttributeError). "
        "Bare `except Exception` silently skips V1 launch check."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
