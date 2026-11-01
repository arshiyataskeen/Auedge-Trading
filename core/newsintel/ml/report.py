"""Plain-HTML report of a walk-forward run: the verdict in words first, then the volatility result, then tables."""
from __future__ import annotations

import html
from pathlib import Path

from ..minutes import DATA
from .harness import MODEL_NAMES, Results

DEFAULT_PATH = DATA / "news_intel_report.html"
RISK_ONLY = "Recommended use: risk only (volatility expectation and AVOID gates), not direction."


def _ci(b) -> str:
    return f"{b[0]:+.4f} (95 % CI {b[1]:+.4f} to {b[2]:+.4f})"


def verdict_lines(r: Results) -> list[str]:
    """The plain-words verdict: forecast check, best single news model, per kind, then volatility."""
    s, t = r.models["Stacker"]["log_loss"], r.models["TechnicalOnly"]["log_loss"]
    b = r.boot_vs_tech["Stacker"]
    does = "does" if r.go_live_forecast else "does not"
    lines = [f"News intelligence {does} beat the technical-only signal on {r.label}: stacker log-loss {s:.4f} vs "
             f"technical-only {t:.4f}, difference {_ci(b)} over {r.n_test} out-of-sample release times "
             f"({r.fold_names[0]}..{r.fold_names[-1]}, {len(r.fold_names)} quarterly folds)."]
    if r.go_live_forecast:
        lines.append("Forecast go-live check PASSES (stacker better than technical-only with the 95 % CI entirely "
                     "below 0). The trading check (R per trade, drawdown) is still to be done.")
    else:
        lines.append("Forecast go-live check FAILS: the stacker is not better than technical-only with a 95 % CI "
                     "entirely below 0. " + RISK_ONLY)
    bn = r.best_news_model
    pool = "Bayes/KNN/LogReg" + ("/Forest" if r.forest_kept else "")
    lines.append(f"Best single news model ({pool}): {bn}, log-loss {r.models[bn]['log_loss']:.4f}, vs technical-only "
                 f"{_ci(r.boot_vs_tech[bn])}. Random forest {'kept' if r.forest_kept else 'dropped'} "
                 f"(Forest - LogReg {_ci(r.forest_vs_logreg)}).")
    for g in r.per_kind:
        lines.append(f"  {g['group']} (n={g['n']}): stacker - technical-only {_ci(g['diff_vs_tech']['Stacker'])}"
                     f"{'  [small sample]' if g['n'] < 30 else ''}")
    v = r.vol
    gain = (v["mae_naive"] - v["mae_model"]) / v["mae_naive"] * 100 if v["mae_naive"] else 0.0
    lines.append(f"Volatility: expected |move60| MAE ${v['mae_model']:.2f} vs naive ${v['mae_naive']:.2f} "
                 f"({gain:+.1f} % {'better' if gain > 0 else 'worse'} than naive, n={v['n']}).")
    return lines


def _table(head: list[str], rows: list[list]) -> str:
    th = "".join(f"<th>{html.escape(str(h))}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(_fmt(c))}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>"


def _fmt(c) -> str:
    if c is None:
        return "-"
    if isinstance(c, float):
        return f"{c:.4f}"
    return str(c)


CSS = """
:root { color-scheme: light dark; --bg:#ffffff; --fg:#1b1b1b; --muted:#666; --line:#d0d0d0; --head:#f2f2f2;
        --good:#1a7f37; --bad:#b42318; }
@media (prefers-color-scheme: dark) { :root { --bg:#141414; --fg:#e8e8e8; --muted:#a0a0a0; --line:#3a3a3a;
        --head:#222; --good:#4ac26b; --bad:#ff7b72; } }
body { background:var(--bg); color:var(--fg); font:14px/1.5 system-ui, sans-serif; margin:24px auto; max-width:1100px;
       padding:0 16px; }
h1 { font-size:22px; } h2 { font-size:17px; margin-top:28px; border-bottom:1px solid var(--line); }
table { border-collapse:collapse; margin:8px 0 16px; font-variant-numeric:tabular-nums; display:block; overflow-x:auto; }
th, td { border:1px solid var(--line); padding:3px 8px; text-align:right; white-space:nowrap; }
th { background:var(--head); } td:first-child, th:first-child { text-align:left; }
.verdict p { margin:4px 0; } .pass { color:var(--good); font-weight:600; } .fail { color:var(--bad); font-weight:600; }
.muted { color:var(--muted); }
"""


def render(r: Results) -> str:
    names = MODEL_NAMES + ["Stacker"]
    vl = verdict_lines(r)
    cls = "pass" if r.go_live_forecast else "fail"
    verdict = (f'<p class="{cls}">{html.escape(vl[0])}</p>'
               + "".join(f"<p>{html.escape(s)}</p>" for s in vl[1:-1]))
    parts = [f"<h1>News intelligence models — {html.escape(r.label)}</h1>",
             '<section class="verdict"><h2>Verdict</h2>' + verdict + "</section>",
             "<h2>Volatility</h2><p>" + html.escape(vl[-1]) + "</p>",
             '<p class="muted">Log-loss: lower is better; uniform guess = 1.0986. Differences are model minus '
             "technical-only per release time, paired bootstrap (2,000 resamples, seed 0); negative = the model is "
             "better.</p>"]

    parts.append("<h2>Pooled out-of-sample metrics</h2>" + _table(
        ["model", "log-loss", "Brier", "accuracy", "n", "vs technical-only", "95 % lo", "95 % hi"],
        [[n, r.models[n]["log_loss"], r.models[n]["brier"], r.models[n]["accuracy"], r.models[n]["n"],
          *(r.boot_vs_tech[n] if n in r.boot_vs_tech else (None, None, None))] for n in names]))

    parts.append("<h2>Per kind group</h2>" + _table(
        ["group", "n"] + names,
        [[g["group"], g["n"]] + [g["log_loss"][n] for n in names] for g in r.per_kind]))
    parts.append(_table(
        ["group", "n", "stacker - technical", "95 % lo", "95 % hi", f"{r.best_news_model} - technical",
         "95 % lo", "95 % hi"],
        [[g["group"], g["n"], *g["diff_vs_tech"]["Stacker"], *g["diff_vs_tech"][r.best_news_model]]
         for g in r.per_kind]))

    parts.append("<h2>Per fold log-loss</h2>" + _table(
        ["fold", "n", "primary", "T"] + names,
        [[f["fold"], f["n"], f["primary"], f["T"]] + [f["log_loss"][n] for n in names] for f in r.per_fold]))
    parts.append(f'<p class="muted">Primary model for the stacker is chosen per fold from earlier folds only '
                 f"(first two folds: LogReg); counts: {html.escape(str(r.primary_counts))}. Random forest "
                 f"{'kept' if r.forest_kept else 'dropped'} as a candidate: Forest - LogReg "
                 f"{html.escape(_ci(r.forest_vs_logreg))}.</p>")

    parts.append("<h2>Reliability (10 bins on the max-probability class)</h2>")
    for n in names:
        parts.append(f"<p>{html.escape(n)}</p>" + _table(
            ["mean confidence", "frequency correct", "n"], [list(row) for row in r.reliability[n]]))

    coefs = sorted(r.logreg_coefs, key=lambda c: -abs(c[2]))
    parts.append(f"<h2>LogReg coefficients (last fold {html.escape(r.fold_names[-1])}, standardised features)</h2>"
                 + _table(["feature", "class", "coef"], [list(c) for c in coefs]))

    parts.append("<h2>KNN neighbours of the 5 largest |move60| test events</h2>")
    for e in r.knn_examples:
        parts.append(f"<p>{html.escape(e['date'])} {html.escape(e['kind'])} z={_fmt(e['z'])} "
                     f"move60={e['move60']:+.2f} ({html.escape(e['label'])}), fold {html.escape(e['fold'])}, "
                     f"k={e['k']}, Bhattacharyya(neighbours vs same kind)={e['bhattacharyya']:.4f}</p>"
                     + _table(["date", "kind", "z", "move60", "label"],
                              [[nb["date"], nb["kind"], nb["z"], nb["move60"], nb["label"]] for nb in e["neighbours"]]))

    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>News intelligence report</title><style>{CSS}</style></head><body>"
            + "".join(parts) + "</body></html>")


def write(r: Results, path: Path = DEFAULT_PATH) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(r), encoding="utf-8")
    return path
