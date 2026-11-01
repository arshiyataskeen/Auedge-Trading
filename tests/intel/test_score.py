import json

from core.intel import score as S


def _all(ok):
    return {k: {"ok": ok, "text": k} for k in S.DEFAULT_WEIGHTS}


def test_all_ok_scores_100_strong():
    q = S.score_factors(_all(True))
    assert q["score"] == 100 and q["band"] == "strong" and not q["avoid"] and q["label"] == ""


def test_all_fail_is_avoid():
    q = S.score_factors(_all(False))
    assert q["score"] == 0 and q["avoid"] and q["label"] == "AVOID"
    assert "below 55" in q["avoid_reasons"][0]


def test_missing_factor_is_neutral_half_weight():
    q = S.score_factors({})
    assert q["score"] == 50
    assert all(r["text"] == S.NA for r in q["factors"])


def test_blocking_gate_forces_avoid_even_with_high_score():
    q = S.score_factors(_all(True), ["News window: CPI."])
    assert q["score"] == 100 and q["avoid"] and q["avoid_reasons"] == ["News window: CPI."]


def test_never_called_a_probability():
    q = S.score_factors(_all(True))
    assert "not a chance of winning" in q["text"] and "probab" not in q["text"].lower()


def test_weights_and_bands_from_file(tmp_path):
    p = tmp_path / "w.json"
    p.write_text(json.dumps({"weights": {"align": 100}, "bands": {"fair": 90}}))
    cfg = S.load_config(p)
    assert cfg["weights"]["align"] == 100 and cfg["bands"]["fair"] == 90
    f = {"align": {"ok": True, "text": ""}}
    q = S.score_factors(f, config=cfg)
    assert q["avoid"]            # big align weight but other factors neutral -> below 90


def test_band_edges():
    b = S.DEFAULT_BANDS
    assert S.band(85, b) == "strong" and S.band(70, b) == "good" and S.band(55, b) == "fair" and S.band(54, b) == "weak"
