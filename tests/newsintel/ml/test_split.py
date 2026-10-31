"""Walk-forward folds: quarterly test sets, 1-day embargo, no overlap; inner folds are time-ordered."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from core.newsintel.ml.split import folds, inner_folds

DAY = 86400


def ts(y, m, d):
    return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp())


def test_folds_quarters_embargo_and_no_overlap():
    t = np.arange(ts(2021, 1, 1), ts(2022, 12, 31), 2 * DAY, dtype=np.int64)
    fs = folds(t)
    assert [f.name for f in fs] == ["2022Q1", "2022Q2", "2022Q3", "2022Q4"]
    starts = [ts(2022, 1, 1), ts(2022, 4, 1), ts(2022, 7, 1), ts(2022, 10, 1)]
    ends = starts[1:] + [ts(2023, 1, 1)]
    for f, a, b in zip(fs, starts, ends):
        assert len(f.train) and len(f.test)
        assert (t[f.train] < a - DAY).all()
        assert ((t[f.test] >= a) & (t[f.test] < b)).all()
        assert not set(f.train) & set(f.test)


def test_partial_last_quarter_excluded():
    t = np.arange(ts(2021, 1, 1), ts(2022, 11, 1), DAY, dtype=np.int64)
    assert [f.name for f in folds(t)] == ["2022Q1", "2022Q2", "2022Q3"]


def test_inner_folds_ordered_and_disjoint():
    idx = np.arange(40)
    inner = inner_folds(idx, 3)
    assert len(inner) == 3
    prev_end = -1
    for tr, va in inner:
        assert not set(tr) & set(va)
        assert tr.max() < va.min()  # validate strictly after train
        assert va.min() > prev_end
        prev_end = va.max()
    assert len(set(np.concatenate([va for _, va in inner]))) == sum(len(va) for _, va in inner)
