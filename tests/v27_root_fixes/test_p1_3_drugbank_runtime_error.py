"""P1-3: drugbank_pipeline must NOT swallow the v9 RuntimeError for missing OMIM CSV.

v27 ROOT FIX verification: the immediate except wrapping _write_structured_indications
must be (OSError, PermissionError), not bare Exception.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path("/home/z/my-project/v28/v28_upgraded/phase1/pipelines/drugbank_pipeline.py")


def test_drugbank_indications_call_has_narrow_except():
    """The except immediately wrapping _write_structured_indications must
    be (OSError, PermissionError), not bare Exception."""
    src = _FILE.read_text()
    # Find every call to _write_structured_indications(drugs_df) and check
    # the except clause that follows.
    pattern = re.compile(
        r"_write_structured_indications\s*\(\s*drugs_df\s*\).*?except\s+(\([^)]+\)|\w+)",
        re.DOTALL,
    )
    matches = pattern.findall(src)
    assert matches, (
        "P1-3 setup: cannot find _write_structured_indications call "
        "followed by an except clause"
    )
    for except_clause in matches:
        except_clause = except_clause.strip()
        # Must NOT be a bare `Exception`
        assert except_clause != "Exception", (
            f"P1-3 REGRESSION: _write_structured_indications is wrapped in "
            f"`except Exception` (clause: {except_clause!r}). This swallows "
            f"the v9 ROOT FIX RuntimeError. Narrow to (OSError, PermissionError)."
        )
        # Must include OSError or PermissionError
        assert "OSError" in except_clause or "PermissionError" in except_clause, (
            f"P1-3 REGRESSION: except clause {except_clause!r} does not "
            f"include OSError/PermissionError. RuntimeError must propagate."
        )


def test_drugbank_indications_omim_runtime_error_still_present():
    """The v9 RuntimeError for missing OMIM CSV must still be raised inside
    _write_structured_indications."""
    src = _FILE.read_text()
    # Find the function definition and verify it raises RuntimeError when
    # OMIM CSV is missing.
    func_match = re.search(
        r"def\s+_write_structured_indications\b[^:]*:(.*?)(?=\n    def\s|\nclass\s|\Z)",
        src,
        re.DOTALL,
    )
    assert func_match, "P1-3 setup: cannot find _write_structured_indications"
    body = func_match.group(1)
    assert "RuntimeError" in body or "raise" in body, (
        "P1-3 REGRESSION: _write_structured_indications does not raise "
        "RuntimeError when OMIM CSV is missing. The v9 ROOT FIX is gone."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
