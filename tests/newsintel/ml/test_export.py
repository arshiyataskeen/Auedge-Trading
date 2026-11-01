"""Export: fitted artifacts round-trip, thresholds follow their stated rules, `until` keeps the future out."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone

import numpy as np
import pytest

from core.indicators import atr
from core.newsintel.bars import resample
from core.newsintel.minutes import Minutes
from core.newsintel.ml import export as E, harness, metrics as M
from core.newsintel.ml.data import FEATURE_NAMES
from core.newsintel.ml.models import KNN, KNN_KS, tune
from core.newsintel.ml.split import folds
from core.newsintel.ml.stack import vol_tables
from core.newsintel.ml.stats import bhattacharyya
from tests.newsintel.ml.test_harness import synth

I = {n: i for i, n in enumerate(FEATURE_NAMES)}


def make_minutes(t0: int, days: int = 5, seed=1) -> Minutes:
    rng = np.random.default_rng(seed)
    n = days * 1440
    t = t0 // 60 * 60 + np.arange(n, dtype=np.int64) * 60
    c = 2000 + np.cumsum(rng.normal(size=n) * 0.3)
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + rng.random(n) * 0.5
    l = np.minimum(o, c) - rng.random(n) * 0.5
    return Minutes(t, o, h, l, c)


@pytest.fixture(scope="module")
def ds():
    return synth()


@pytest.fixture(scope="module")
def mins(ds):
    return make_minutes(int(ds.t[20]))


@pytest.fixture(scope="module")
def res(ds):
    return harness.run(ds)


@pytest.fixture(scope="module")
def exported(ds, mins, tmp_path_factory):
    out = tmp_path_factory.mktemp("models")
    meta = E.export(ds, out, minutes=mins)
    return out, meta, E.load_artifacts(out)


def test_export_roundtrip(ds, res, exported):
    out, meta, art = exported
    assert isinstance(art, E.Artifacts)
    idx = np.arange(len(ds.t))
    p = M.apply_temperature(art.primary.predict_proba(ds, idx), art.temperature)
    sp = art.stacker.predict_proba(ds, idx, p)
    assert sp.shape == (len(idx), 3) and np.allclose(sp.sum(axis=1), 1.0)
    assert art.technical.predict_proba(ds, idx).shape == (len(idx), 3)
    assert art.go_live == res.go_live_forecast
    on_disk = json.loads((out / "meta.json").read_text())
    assert on_disk == meta
    assert on_disk["go_live"] == res.go_live_forecast and on_disk["primary_name"] == art.primary_name
    assert art.trained_through == datetime.fromtimestamp(int(ds.t[-1]), timezone.utc).strftime("%Y-%m-%d")
    assert art.version and meta["trained_until"] is None
    assert art.neighbours_X.shape[0] == len(ds.t) == len(art.neighbours_meta["move60"])
    assert art.stats_rows and sum(r["n"] for r in art.stats_rows) == len(ds.t)


def test_load_missing_returns_none(tmp_path):
    assert E.load_artifacts(tmp_path / "nothing") is None


def test_vol_table_matches_harness_rule(ds, exported):
    art = exported[2]
    big = (ds.X[:, I["abs_z"]] >= 1.0) & (ds.X[:, I["z_missing"]] < 0.5)
    ratio = ds.absmove60 / ds.atr15
    checked = 0
    for kind in np.unique(ds.kind):
        for b in (False, True):
            m = (ds.kind == kind) & (big == b)
            if m.sum() >= 5:
                assert art.vol_table[(str(kind), b)] == pytest.approx(np.median(ratio[m]))
                checked += 1
        assert art.vol_kind[str(kind)] == pytest.approx(np.median(ratio[ds.kind == kind]))
    assert checked >= 4
    assert art.vol_overall == pytest.approx(np.median(ratio))


def test_vol_table_small_bucket_falls_back_to_kind_then_overall():
    d = synth(100)
    d.X[:, I["abs_z"]] = 0.0  # nobody is "big" ...
    ppi = np.flatnonzero(d.kind == "PPI")
    d.X[ppi[:3], I["abs_z"]] = 2.0  # ... except 3 PPI rows: below the 5-row minimum
    table, by_kind, overall = vol_tables(d, np.arange(100))
    ratio = d.absmove60 / d.atr15
    assert table[("PPI", True)] == pytest.approx(np.median(ratio[ppi]))  # falls back to the kind median
    assert table[("PPI", False)] == pytest.approx(np.median(ratio[ppi[3:]]))
    assert table[("NFP", True)] == pytest.approx(by_kind["NFP"])  # no big NFP rows at all
    assert overall == pytest.approx(np.median(ratio))
    # a kind with fewer than 5 rows in total falls back to the overall median
    d2 = replace(d, kind=np.where(np.arange(100) < 3, "GDP", d.kind))
    t2, k2, o2 = vol_tables(d2, np.arange(100))
    assert k2["GDP"] == o2 and t2[("GDP", False)] == o2 and t2[("GDP", True)] == o2


def _fake(res, **losses):
    models = {n: dict(v) for n, v in res.models.items()}
    for n, ll in losses.items():
        models[n]["log_loss"] = ll
    return models


def test_primary_choice_uses_pooled_oos_over_all_folds(res):
    base = dict(Bayes=1.0, KNN=1.1, LogReg=1.2, Forest=0.5)
    assert E.choose_primary(replace(res, models=_fake(res, **base), forest_kept=False)) == "Bayes"
    assert E.choose_primary(replace(res, models=_fake(res, **{**base, "KNN": 0.9}), forest_kept=False)) == "KNN"
    assert E.choose_primary(replace(res, models=_fake(res, **{**base, "LogReg": 0.8}), forest_kept=False)) == "LogReg"
    # Forest only counts when it beat LogReg with the CI below 0
    assert E.choose_primary(replace(res, models=_fake(res, **base), forest_kept=True)) == "Forest"
    # ties go to the earlier candidate
    assert E.choose_primary(replace(res, models=_fake(res, **dict.fromkeys(base, 1.0)), forest_kept=True)) == "Bayes"


def test_export_fits_the_chosen_primary(ds, res, mins, tmp_path, monkeypatch):
    forced = replace(res, models=_fake(res, Forest=0.1), forest_kept=True)
    monkeypatch.setattr(harness, "run", lambda *a, **k: forced)
    E.export(ds, tmp_path, minutes=mins)
    art = E.load_artifacts(tmp_path)
    assert art.primary_name == "Forest" and art.primary.name == "Forest"
    forced = replace(res, models=_fake(res, Forest=0.1), forest_kept=False)
    monkeypatch.setattr(harness, "run", lambda *a, **k: forced)
    E.export(ds, tmp_path, minutes=mins)
    assert E.load_artifacts(tmp_path).primary_name == E.choose_primary(forced) != "Forest"


def test_primary_in_real_export_is_choose_primary(res, exported):
    assert exported[2].primary_name == E.choose_primary(res)


def _near_event(t, events):
    return any(e - 1800 < t + 300 and t < e + 10800 for e in events)


def test_thresholds(ds, res, mins, exported):
    art = exported[2]
    max_p = np.vstack(res.stacker_probs).max(axis=1)
    assert art.uncertain_max_p == pytest.approx(np.percentile(max_p, 20))

    # neighbour distances, computed row by row with the model's own neighbours()
    def r(ix):
        return np.where(ds.atr15[ix] > 0, ds.move60[ix] / np.where(ds.atr15[ix] > 0, ds.atr15[ix], 1.0), 0.0)

    d = []
    for f in folds(ds.t):
        knn = tune(KNN, KNN_KS, ds, f.train)
        for i in f.test:
            nb = np.array(knn.neighbours(ds, int(i), f.train, knn.k))
            same = f.train[ds.kind[f.train] == ds.kind[i]]
            d.append(bhattacharyya(r(nb), r(same)))
    assert len(d) == len(max_p)
    assert art.uncertain_bhatt == pytest.approx(np.percentile(d, 80))

    # M5 range / ATR(14) of 5-minute bars outside every event window; reference via core.indicators.atr
    bars = resample(mins, 300, int(mins.t[-1]) + 60, 10**6)
    a = atr(bars, 14)
    events = [int(x) for x in ds.t]
    ref = [(b.h - b.l) / x for b, x in zip(bars, a) if x and not _near_event(b.t, events)]
    assert 100 < len(ref) < len(bars) - 14  # some bars were excluded
    assert art.m5_range_p99 == pytest.approx(np.percentile(ref, 99))


def test_m5_range_ignores_event_windows():
    m = make_minutes(1_700_000_000, days=2)
    event = int(m.t[1500])
    base = E.m5_range_ratio(m, [event])
    spiked = Minutes(m.t, m.o, m.h.copy(), m.l.copy(), m.c)
    spiked.h[(m.t >= event - 20 * 60) & (m.t < event + 150 * 60)] += 500.0  # inside -30 .. +180 min
    after = E.m5_range_ratio(spiked, [event])
    assert len(after) == len(base) and after.max() < 2 * base.max()  # the spike bars never enter the sample
    assert E.m5_range_ratio(spiked, []).max() > 5 * base.max()  # ... but they would without the event window
    assert len(E.m5_range_ratio(m, [])) > len(base)


def _cut(until):
    return int(datetime.strptime(until, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def test_until_keeps_the_future_out(ds, tmp_path):
    until = "2022-10-01"
    cut = _cut(until)
    mins = make_minutes(cut - 2 * 86400, days=4)  # candles on both sides of the cut
    ds = replace(ds, t=ds.t.copy())
    j = int(np.flatnonzero(ds.t < cut)[-1])
    ds.t[j] = cut - 30 * 60  # a release whose 60/120-minute label window runs past the cut
    late = ds.t + 7200 >= cut  # label window not finished before the cut
    after = mins.t >= cut - 7200
    assert late[j] and late.sum() > 1 and (~late).any() and after.any() and (~after).any()
    clean = E.export(ds, tmp_path / "a", until=until, minutes=mins)
    # wreck everything whose window reaches the cut: features, labels, moves, candles
    bad = replace(ds, X=ds.X.copy(), y=ds.y.copy(), y120=ds.y120.copy(), absmove60=ds.absmove60.copy(),
                  atr15=ds.atr15.copy(), move60=ds.move60.copy())
    bad.X[late] = bad.X[late] * 7 + 3
    bad.y[late] = (bad.y[late] + 1) % 3
    bad.y120[late] = bad.y[late]
    bad.move60[late] *= -50
    bad.absmove60[late] = np.abs(bad.move60[late])
    bad.atr15[late] *= 9
    wild = Minutes(mins.t, mins.o, mins.h.copy(), mins.l.copy(), mins.c)
    wild.h[after] += 1000.0  # includes the last 120 minutes before the cut
    dirty = E.export(bad, tmp_path / "b", until=until, minutes=wild)
    for k in clean:
        if k != "version":
            assert clean[k] == dirty[k], k
    a, b = E.load_artifacts(tmp_path / "a"), E.load_artifacts(tmp_path / "b")
    assert a.trained_until == until and a.trained_through < until
    assert len(a.neighbours_X) == int((~late).sum())
    assert a.neighbours_meta["t"].max() + 7200 < cut
    assert np.array_equal(a.neighbours_X, b.neighbours_X) and a.vol_table == b.vol_table
    assert a.stats_rows == b.stats_rows and a.m5_range_p99 == b.m5_range_p99


def test_truncate_recounts_missing_feature_rows(ds):
    flags = np.zeros(len(ds.t), dtype=bool)
    flags[[0, 1, len(flags) - 1]] = True  # two early rows, one at the very end
    d = replace(ds, none_row=flags, n_none_features=3)
    cut = int(ds.t[100]) + 7201
    out = E.truncate(d, datetime.fromtimestamp(cut, timezone.utc).strftime("%Y-%m-%d"))
    assert len(out.t) < len(d.t)
    assert out.n_none_features == int(out.none_row.sum()) == 2
    assert E.truncate(replace(ds, n_none_features=5), "2022-10-01").n_none_features == 5  # no per-row flags to recount


def test_load_corrupt_files_return_none(exported, tmp_path, capsys):
    src = exported[0]
    raw = (src / "models.pkl").read_bytes()
    (tmp_path / "meta.json").write_text((src / "meta.json").read_text())
    (tmp_path / "models.pkl").write_bytes(raw[: len(raw) // 2])  # truncated pickle
    assert E.load_artifacts(tmp_path) is None
    assert capsys.readouterr().err.startswith("[newsintel] models unavailable: ")
    (tmp_path / "models.pkl").write_bytes(b"not a pickle at all")
    assert E.load_artifacts(tmp_path) is None
    (tmp_path / "models.pkl").write_bytes(raw)
    assert E.load_artifacts(tmp_path) is not None
    (tmp_path / "meta.json").write_text("{garbage")
    assert E.load_artifacts(tmp_path) is None
    assert "[newsintel] models unavailable: " in capsys.readouterr().err


def test_cli_rejects_bad_until(capsys):
    from core.newsintel.ml.__main__ import main
    for bad in ("2025-8-1x", "01/08/2025", "2025-13-01"):
        with pytest.raises(SystemExit) as e:
            main(["--export", "--until", bad])
        assert e.value.code == 2
    assert "YYYY-MM-DD" in capsys.readouterr().err
