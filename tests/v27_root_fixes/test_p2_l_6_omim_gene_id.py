"""P2-L-6: omim_loader must use canonical_gene_id -> ncbi_gene_id -> gene_mim priority.

ROOT-CAUSE BEING VERIFIED:
  omim_loader used ONLY gene_mim via _safe_gene_id_from_mim. Phase 1
  emits gene_mim, ncbi_gene_id, canonical_gene_id. phase1_bridge
  correctly prefers canonical_gene_id -> ncbi_gene_id -> gene_mim.
  omim_loader didn't — same gene became 2 KG nodes.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path("/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/omim_loader.py")


def test_omim_loader_uses_canonical_gene_id_priority():
    src = _FILE.read_text()
    # Must reference canonical_gene_id and ncbi_gene_id (not just gene_mim)
    assert "canonical_gene_id" in src, (
        "P2-L-6 REGRESSION: omim_loader does not check canonical_gene_id. "
        "Same gene becomes 2 KG nodes (one via canonical_gene_id from "
        "phase1_bridge, one via gene_mim from omim_loader)."
    )
    assert "ncbi_gene_id" in src, (
        "P2-L-6 REGRESSION: omim_loader does not check ncbi_gene_id."
    )


def test_omim_loader_priority_order():
    """The priority order must be canonical_gene_id -> ncbi_gene_id -> gene_mim."""
    src = _FILE.read_text()
    # Find the resolver function
    # Look for the pattern: check canonical_gene_id FIRST, then ncbi_gene_id, then gene_mim
    canonical_pos = src.find("canonical_gene_id")
    ncbi_pos = src.find("ncbi_gene_id")
    mim_pos = src.find("gene_mim")
    # All three must be present
    assert canonical_pos >= 0 and ncbi_pos >= 0 and mim_pos >= 0
    # In the resolver function, canonical must come before ncbi must come before mim
    # (we allow it to appear in other places too, but find the resolver function)
    # For a robust check, find the function that resolves gene IDs
    resolver_match = re.search(
        r"def\s+(_resolve_gene_id|_resolve_gene_id_omim|_get_gene_id)\b[^:]*:(.*?)\n    def\s",
        src,
        re.DOTALL,
    )
    if resolver_match:
        body = resolver_match.group(2)
        c = body.find("canonical_gene_id")
        n = body.find("ncbi_gene_id")
        m = body.find("gene_mim")
        if c >= 0 and n >= 0 and m >= 0:
            assert c < n < m, (
                "P2-L-6 REGRESSION: priority order is wrong. Must be "
                "canonical_gene_id -> ncbi_gene_id -> gene_mim (mirrors "
                "phase1_bridge)."
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
