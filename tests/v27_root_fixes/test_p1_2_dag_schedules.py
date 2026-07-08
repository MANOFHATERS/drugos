"""P1-2: 4 standalone DAGs must have schedule=None (mirror chembl_dag.py).

ROOT-CAUSE BEING VERIFIED:
  The v9 ROOT FIX comment in chembl_dag.py explains why standalone schedules
  were disabled for chembl/pubchem/uniprot (cause double-ingest collisions
  with the master DAG on Sundays). The fix was never applied to
  disgenet/drugbank/omim/string DAGs — they still had monthly cron schedules.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_DAG_DIR = Path("/home/z/my-project/v28/v28_upgraded/phase1/dags")
_BROKEN_DAGS = ["disgenet_dag.py", "drugbank_dag.py", "omim_dag.py", "string_dag.py"]
_OK_DAGS = ["chembl_dag.py", "pubchem_dag.py", "uniprot_dag.py"]


@pytest.mark.parametrize("dag_file", _BROKEN_DAGS)
def test_broken_dags_now_have_schedule_none(dag_file):
    """All 4 previously-broken DAGs must now have schedule=None."""
    src = (_DAG_DIR / dag_file).read_text()
    # Must have schedule=None
    assert re.search(r"schedule\s*=\s*None", src), (
        f"P1-2 REGRESSION: {dag_file} does not have schedule=None. "
        f"Standalone schedules cause double-ingest collisions with the "
        f"master DAG (v9 ROOT FIX comment in chembl_dag.py explains why)."
    )
    # Must NOT have monthly cron schedule
    assert not re.search(r"schedule\s*=\s*[\"']0 \d+ 1 \* \*[\"']", src), (
        f"P1-2 REGRESSION: {dag_file} still has a monthly cron schedule."
    )


@pytest.mark.parametrize("dag_file", _OK_DAGS + _BROKEN_DAGS)
def test_all_dags_have_schedule_none(dag_file):
    """All 7 DAGs should now have schedule=None for consistency."""
    src = (_DAG_DIR / dag_file).read_text()
    assert re.search(r"schedule\s*=\s*None", src), (
        f"P1-2 REGRESSION: {dag_file} does not have schedule=None."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
