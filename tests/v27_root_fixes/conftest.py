"""Pytest configuration for v27 root-fix verification tests.

Adds phase1/ and phase2/ to sys.path so test modules can import the
production code under audit.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]  # v27_upgraded/
_PHASE1 = _ROOT / "phase1"
_PHASE2 = _ROOT / "phase2"

for p in (str(_ROOT), str(_PHASE1), str(_PHASE2)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("DRUGOS_ENVIRONMENT", "development")
os.environ.setdefault("DRUGOS_SKIP_DOWNLOAD", "1")
os.environ.setdefault("DRUGOS_SKIP_NEO4J", "1")
