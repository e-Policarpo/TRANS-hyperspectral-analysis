"""A sweep on worker processes must write the rows the serial loop writes.

Each spectrum builds its own seeded Designer, so the schedule cannot change
an answer; these tests hold the parallel path to that, and to Cancel.
"""

import json

import pandas as pd
import pytest

from src.backend import designer_pool
from src.backend.designer_pool import resolve_workers
from tests.test_backend.test_designer_consensus import (SEARCH, TWO_WELLS,
                                                       MockTask, _run, _table)


def _rows(tool):
    frame = _table(tool, "Candidates").copy()
    return frame.sort_values(list(frame.columns[:3])).reset_index(drop=True)


def test_parallel_sweep_writes_the_serial_rows(tmp_path):
    serial_tool, serial = _run(tmp_path / "serial", TWO_WELLS, workers=1)
    pool_tool, pooled = _run(tmp_path / "pool", TWO_WELLS, workers=3)

    assert pooled['spectra_searched'] == serial['spectra_searched'] == 6
    assert pooled['candidates_total'] == serial['candidates_total'] > 0
    pd.testing.assert_frame_equal(_rows(pool_tool), _rows(serial_tool))
    # As JSON: the consensus carries NaN for the dimensions a 1D well does
    # not have, and NaN != NaN would fail a dict comparison of equal runs.
    assert (json.dumps(pooled['consensus'], sort_keys=True, default=str)
            == json.dumps(serial['consensus'], sort_keys=True, default=str))


def test_a_cancelled_pool_registers_nothing(tmp_path):
    class CancelledTask(MockTask):
        cancelled = True

    from tests.test_backend.test_designer_consensus import _backend, _dataset
    tool = _backend(tmp_path)
    tool._datasets['sts'] = _dataset(TWO_WELLS)
    result = tool.design_confinement(CancelledTask(), 'sts',
                                     {**SEARCH, 'workers': 3})
    assert result['error'] == 'Cancelled'
    assert list(tool._datasets) == ['sts']


@pytest.mark.parametrize('requested,n,expected', [
    (1, 50, 1),            # asked for serial
    (4, 50, 4),            # a ceiling
    (8, 5, 5),             # never more workers than spectra
    (8, 2, 1),             # too few spectra to repay the start-up
    (0, 50, designer_pool.default_workers()),
    (None, 50, designer_pool.default_workers()),
])
def test_worker_count(requested, n, expected):
    assert resolve_workers(requested, n) == expected
