import numpy as np

from core.newsintel.fred import Release
from core.newsintel.surprise import expectations


def _rels(values):
    return [Release(f"2020-01-{i + 1:02d}", f"2020-02-{i + 1:02d}", v, None)
            for i, v in enumerate(values)]


def _ar_series(n=60):
    rng = np.random.default_rng(0)
    y = [2.0]
    for _ in range(n - 1):
        y.append(1 + 0.5 * y[-1] + rng.normal(0, 0.01))
    return y


def test_no_lookahead():
    y = _ar_series(40)
    base = expectations(_rels(y), 1)
    for i in (5, 20, 30):
        changed = list(y)
        changed[i + 1] += 50.0
        out = expectations(_rels(changed), 1)
        assert out[: i + 1] == base[: i + 1]
        assert out[i] == base[i]


def test_ar1_on_known_series():
    y = _ar_series(60)
    out = expectations(_rels(y), 1)
    assert out[-1].expected is not None
    assert abs(out[-1].expected - (1 + 0.5 * y[-2])) < 0.05
    assert out[-1].sigma is not None and out[-1].sigma < 0.05


def test_sign_orientation():
    y = _ar_series(40)
    pos = expectations(_rels(y), 1)
    neg = expectations(_rels(y), -1)
    for p, n in zip(pos, neg):
        if p.z is None:
            assert n.z is None
        else:
            assert n.z == -p.z
    assert pos[-1].z is not None


def test_short_history_fallback():
    out = expectations(_rels([1.0, 2.0, 4.0, 3.0, 5.0]), 1)
    assert [o.expected for o in out[:3]] == [None, None, None]
    assert out[3].expected == 4.0
    assert out[4].expected == 3.0
    assert out[4].release_date == "2020-02-05"
    assert out[4].sigma is not None
    assert out[4].z is not None


def test_zero_sigma_gives_no_z():
    out = expectations(_rels([1.0, 1.0, 1.0, 1.0, 2.0]), 1)
    assert out[4].expected == 1.0
    assert out[4].z is None
