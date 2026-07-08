"""TOP-24: Makefile clean must NOT swallow all errors in RECIPE lines.

ROOT-CAUSE: `2>/dev/null || true` swallowed all errors. Operators never
see real failures. ALSO: Makefile used 8-space indentation instead of
TABs — every `make` command was failing with "missing separator".

NOTE: The fix may reference the old buggy pattern in COMMENTS explaining
what was removed. That's fine. We only check RECIPE lines.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path("/home/z/my-project/v28/v28_upgraded/Makefile")


def test_makefile_clean_recipe_does_not_swallow_errors():
    """Recipe lines (TAB-indented) under `clean:` must NOT use
    `2>/dev/null || true`."""
    src = _FILE.read_text()
    lines = src.split("\n")
    in_clean = False
    in_recipe = False
    for line in lines:
        # Detect target lines
        if line and not line.startswith(" ") and not line.startswith("\t"):
            in_clean = line.startswith("clean:")
            in_recipe = False
            continue
        if in_clean:
            if line.startswith("\t"):
                # This is a recipe line — check for the buggy pattern
                # but ONLY in the actual command, not in comments
                # Strip leading TAB
                cmd = line[1:]
                # Skip comment lines (TAB then #)
                if cmd.lstrip().startswith("#"):
                    continue
                # Check if the command itself uses the buggy pattern
                assert "2>/dev/null || true" not in cmd, (
                    f"TOP-24 REGRESSION: Makefile clean target recipe line "
                    f"uses `2>/dev/null || true`. Operators never see real "
                    f"failures. Line: {line!r}"
                )
            elif line.startswith("        "):  # 8 spaces — also a recipe but buggy
                cmd = line[8:]
                if cmd.lstrip().startswith("#"):
                    continue
                assert "2>/dev/null || true" not in cmd, (
                    f"TOP-24 REGRESSION: Makefile clean recipe uses buggy "
                    f"pattern. Line: {line!r}"
                )


def test_makefile_uses_tabs_not_spaces():
    """Makefiles REQUIRE TAB indentation. 8-space indentation causes
    'missing separator' errors on every make command."""
    src = _FILE.read_text()
    lines = src.split("\n")
    in_recipe = False
    space_indented_recipes = 0
    tab_indented_recipes = 0
    for line in lines:
        if line and not line.startswith(" ") and not line.startswith("\t"):
            in_recipe = False
            if ":" in line and not line.startswith("#"):
                in_recipe = True
            continue
        if in_recipe:
            if line.startswith("\t"):
                tab_indented_recipes += 1
            elif line.startswith("        "):  # 8 spaces
                space_indented_recipes += 1
    assert space_indented_recipes == 0, (
        f"TOP-24 REGRESSION: Makefile has {space_indented_recipes} recipe "
        f"lines indented with 8 spaces instead of TABs. Every make command "
        f"fails with 'missing separator'."
    )
    assert tab_indented_recipes > 0, "TOP-24 setup: no TAB-indented recipes found"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
