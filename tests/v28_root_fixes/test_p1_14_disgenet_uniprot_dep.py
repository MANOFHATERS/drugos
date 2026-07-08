"""P1-14: DisGeNET _assert_uniprot_dependency must NOT swallow DB errors.

ROOT-CAUSE: broad `except Exception` caught OperationalError/IntegrityError
and only logged warning. Dependency check silently bypassed on transient
DB issues → 100% GDA records failed UniProt resolution.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase1/pipelines/disgenet_pipeline.py"
)


def test_assert_uniprot_dependency_does_not_swallow_db_errors():
    """The except clause in _assert_uniprot_dependency must NOT be bare
    `except Exception`. Must be narrow (ImportError only)."""
    src = _FILE.read_text()
    # Find the _assert_uniprot_dependency method body
    m = re.search(
        r"def\s+_assert_uniprot_dependency\b[^:]*:(.*?)(?=\n    def\s|\nclass\s|\Z)",
        src,
        re.DOTALL,
    )
    assert m, "P1-14 setup: cannot find _assert_uniprot_dependency"
    body = m.group(1)

    # Strip docstrings (triple-quoted) and comments from the body
    # so we only check live code
    body_no_docstrings = re.sub(r'""".*?"""', '', body, flags=re.DOTALL)
    body_no_docstrings = re.sub(r"'''.*?'''", '', body_no_docstrings, flags=re.DOTALL)
    live_lines = []
    for line in body_no_docstrings.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if "#" in line:
            line = line[: line.index("#")]
        live_lines.append(line)
    live_body = "\n".join(live_lines)

    # Must NOT have bare `except Exception` in live code
    bare = re.search(r"except\s+Exception\b", live_body)
    assert not bare, (
        "P1-14 REGRESSION: _assert_uniprot_dependency still has "
        "`except Exception` in live code — swallows OperationalError/"
        "IntegrityError. Narrow to ImportError only."
    )
    # Must have narrow except (ImportError)
    assert "ImportError" in live_body, (
        "P1-14 REGRESSION: _assert_uniprot_dependency does not catch "
        "ImportError (the only non-critical case)."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
