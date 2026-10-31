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


def _rels_dated(obs_dates, values):
    return [Release(d, f"r{i:04d}", v, None) for i, (d, v) in enumerate(zip(obs_dates, values))]


def _monthly(n, start=2014):
    return [f"{start + i // 12}-{i % 12 + 1:02d}-01" for i in range(n)]


def test_huge_outlier_does_not_mute_later_surprises():
    y = _ar_series(80)
    y[40] += 2.0  # one print 200x the noise (outside the COVID window by date)
    out = expectations(_rels(y), 1)
    # 39 releases later, a normal-size surprise (5x the noise) still reads as a surprise;
    # with sigma = std of all residuals it would be z ~ 0.2
    late = list(y)
    late[-1] = 1 + 0.5 * y[-2] + 0.05
    z = expectations(_rels(late), 1)[-1].z
    assert z is not None and z > 1
    assert out[-1].sigma < 0.05


def test_covid_window_excluded_from_history():
    dates = _monthly(110)  # 2014-01 .. 2023-02
    y = _ar_series(110)
    base = expectations(_rels_dated(dates, y), 1)
    wild = list(y)
    covid = [i for i, d in enumerate(dates) if "2020-03-01" <= d <= "2021-06-30"]
    assert len(covid) == 16
    for i in covid:
        wild[i] += 1000.0 * (1 if i % 2 else -1)
    out = expectations(_rels_dated(dates, wild), 1)
    after = covid[-1] + 1
    # releases after the window never see the COVID prints
    assert [(o.expected, o.sigma, o.z) for o in out[after:]] == [(b.expected, b.sigma, b.z) for b in base[after:]]
    # COVID releases still get a forecast from their own (pre-COVID) history
    first = out[covid[0]]
    assert first.expected is not None and first.sigma is not None and first.z is not None
    assert first.expected == base[covid[0]].expected


def test_tiny_sigma_gives_no_z():
    y = [1.0 + 0.5 * i for i in range(40)]  # exact linear: AR residuals ~ 0
    out = expectations(_rels(y), 1)
    assert out[-1].sigma is not None and out[-1].sigma < 1e-12
    assert out[-1].z is None


def test_missing_actual_skipped():
    y = _ar_series(40)
    with_gap = list(y)
    with_gap[30] = None
    out = expectations(_rels(with_gap), 1)
    assert (out[30].expected, out[30].sigma, out[30].z) == (None, None, None)
    ref = expectations(_rels(y[:30] + y[31:]), 1)
    assert out[31].expected == ref[30].expected and out[31].sigma == ref[30].sigma
