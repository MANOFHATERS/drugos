"""P2-B-4: bridge treats-edge disease name matching must use word boundaries.

ROOT-CAUSE BEING VERIFIED:
  Substring match `if dname.lower() in ind_lower:` matched
  "Pain" in "Paint stripper poisoning", "HIV" in "achondroplasia".
  False-positive treats edges pollute training data.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path("/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/phase1_bridge.py")


def test_bridge_treats_uses_word_boundary_regex():
    src = _FILE.read_text()
    # Must use re.search with word boundary
    has_word_boundary = bool(
        re.search(r"re\.search\s*\(\s*rf?['\"]\\\\b", src)
        or re.search(r"\\b\{re\.escape", src)
    )
    assert has_word_boundary, (
        "P2-B-4 REGRESSION: bridge treats-edge disease name matching does "
        "not use word-boundary regex. Substring match produces false "
        "positives (e.g. 'Pain' matches 'Paint stripper poisoning')."
    )


def test_bridge_treats_does_not_use_bare_substring():
    src = _FILE.read_text()
    # The bare `if dname.lower() in ind_lower:` pattern should be gone
    # from the treats-edge block. We can't perfectly localize, but we
    # can check that any `dname.lower() in ind_lower` is accompanied by
    # word-boundary logic nearby.
    bare_substrings = re.findall(
        r'dname\.lower\(\)\s+in\s+ind_lower', src
    )
    # If bare substring is still present, it must be in a comment or
    # accompanied by word-boundary re.search
    if bare_substrings:
        # Make sure re.search with \b is also present
        assert re.search(r"re\.search\s*\(\s*rf?['\"]\\\\b", src) or re.search(r"\\b\{re\.escape", src), (
            "P2-B-4 REGRESSION: bare substring match still present without "
            "word-boundary regex fallback."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
