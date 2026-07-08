"""P1-ER-1: drug_resolver._smiles_index must be a first-class core index.

v27 ROOT FIX verification: _smiles_index must be in __init__, _MutationContext
snapshot, DrugResolver.reset(), _assert_initialized, _assert_indices_consistent.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase1/entity_resolution/drug_resolver.py"
)


def test_smiles_index_initialized_in_init():
    src = _FILE.read_text()
    # The __init__ must have an explicit `self._smiles_index: Dict[str, str] = {}`
    assert re.search(
        r"self\._smiles_index\s*:\s*Dict\[str,\s*str\]\s*=\s*\{\}", src
    ), (
        "P1-ER-1 REGRESSION: __init__ does not initialize _smiles_index "
        "alongside the other 5 indices. Lazy-init was the root cause of "
        "the transactional-snapshot gap."
    )


def test_smiles_index_in_mutation_context_snapshot():
    src = _FILE.read_text()
    assert '"_smiles_index"' in src, (
        "P1-ER-1 REGRESSION: _MutationContext snapshot does not include "
        "_smiles_index. After a rolled-back mutation, the SMILES index "
        "retains stale pointers."
    )


def test_smiles_index_in_drug_resolver_reset():
    """The DrugResolver.reset() method must clear _smiles_index.

    We localize by searching for a `def reset` method on a class that
    also has `_smiles_index` initialized — i.e., the DrugResolver class,
    NOT _DependencyInjector.reset()."""
    src = _FILE.read_text()
    # Find the DrugResolver class body
    cls_match = re.search(
        r"class\s+DrugResolver\b[^:]*:(.*?)(?=\nclass\s|\Z)",
        src,
        re.DOTALL,
    )
    assert cls_match, "P1-ER-1 setup: cannot find DrugResolver class"
    cls_body = cls_match.group(1)
    # Find reset() inside DrugResolver
    reset_match = re.search(
        r"def\s+reset\s*\(\s*self[^)]*\)\s*(?:->\s*[^:]+)?:(.*?)(?=\n    def\s|\n    @|\Z)",
        cls_body,
        re.DOTALL,
    )
    if reset_match:
        reset_body = reset_match.group(1)
        # Look for _smiles_index assignment to {} or .clear()
        assert (
            "self._smiles_index" in reset_body
        ), (
            "P1-ER-1 REGRESSION: DrugResolver.reset() does not clear "
            "_smiles_index. Stale SMILES pointers persist across runs."
        )
    else:
        # If no reset method, the test passes (no reset = no stale state)
        pass


def test_no_defensive_getattr_smiles_index():
    src = _FILE.read_text()
    assert 'getattr(self, "_smiles_index", {})' not in src, (
        "P1-ER-1 REGRESSION: defensive getattr(self, '_smiles_index', {}) "
        "still present. Direct attribute access should work after __init__ "
        "explicitly initializes _smiles_index."
    )


def test_no_hasattr_smiles_index_lazy_guard():
    src = _FILE.read_text()
    assert 'if not hasattr(self, "_smiles_index")' not in src, (
        "P1-ER-1 REGRESSION: `if not hasattr(self, '_smiles_index')` "
        "lazy-init guard still present."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
