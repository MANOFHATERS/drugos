"""P2-B-6: RecordingGraphBuilder must raise on unknown labels (mirror production).

ROOT-CAUSE: returned True for unknown labels. Production kg_builder raises
UnknownLabelError. Tests pass with typo'd labels, production crashes.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/phase1_bridge.py"
)


def test_recording_graph_builder_does_not_accept_unknown_labels():
    src = _FILE.read_text()
    # The buggy pattern: `return True  # unknown label — accept (mirror production)`
    assert "return True  # unknown label" not in src, (
        "P2-B-6 REGRESSION: RecordingGraphBuilder._validate_node_id still "
        "returns True for unknown labels. Tests pass with typo'd labels, "
        "production crashes."
    )


def test_recording_graph_builder_raises_on_unknown_label():
    src = _FILE.read_text()
    # The fix should raise UnknownLabelError (or similar) for unknown labels
    assert (
        "UnknownLabelError" in src
        or "raise" in src
        and "unknown" in src.lower()
    ), (
        "P2-B-6 REGRESSION: RecordingGraphBuilder does not raise on unknown labels."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
