// AuEdge journal: app-style home with your prop-firm accounts, phase-wise trading journal, rule checks.
// Uses helpers from index.html ($, esc, fmt, lsGet, lsSet, equitySvg, agentState). Data: /api/journal/* (data/journal.db).
const J = { accounts: [], acc: null, phaseSel: null, archived: false, page: "home", sub: lsGet("jSub", "journal"), calMonth: null, calDay: null,
            rec: { trades: [], f: {}, cal: false } };
const jUsd = v => v == null ? "—" : `${v < 0 ? "−" : v > 0 ? "+" : ""}$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
const jMoney = v => v == null ? "—" : "$" + Math.round(v).toLocaleString();
const jCls = v => v > 0 ? "up" : v < 0 ? "dn" : "";
const jDate = ts => ts ? new Date(ts * 1000).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—";
const jDay = ts => ts ? new Date(ts * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "—";
const toLocalInput = ts => ts ? new Date(ts * 1000 - new Date(ts * 1000).getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "";
const fromLocalInput = v => v ? Math.round(Date.parse(v) / 1000) : null;
const jApi = async (url, method = "GET", body) => {
  const r = await fetch(url, { method, cache: "no-store", headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
  return r.json();
};
const STATUS = {
  active: ["NA", "In progress"], target_reached: ["BUY", "Target reached ✓"], need_days: ["NA", "Target hit · more days needed"],
  breached: ["SELL", "Rule broken"], passed: ["BUY", "Passed"], failed: ["SELL", "Failed"],
  need_consistency: ["NA", "Target hit · consistency rule"],
};
const EMOTIONS = ["Calm", "Confident", "Patient", "Fearful", "Greedy", "FOMO", "Revenge", "Tired", "Bored"];
const SETUPS = ["AuEdge NOW call", "Stop hunt + reclaim", "London sweep", "Breakout", "Pullback to level", "Range fade", "News"];
const PRESETS = {
  two: { name: "2-step", phases: [{ name: "Phase 1", target_pct: 10, daily_loss_pct: 5, max_loss_pct: 10, max_loss_type: "static", min_days: 4 },
                                  { name: "Phase 2", target_pct: 5, daily_loss_pct: 5, max_loss_pct: 10, max_loss_type: "static", min_days: 4 }],
         funded: { daily_loss_pct: 5, max_loss_pct: 10, max_loss_type: "static", profit_split: 80 } },
  one: { name: "1-step", phases: [{ name: "Phase 1", target_pct: 10, daily_loss_pct: 4, max_loss_pct: 6, max_loss_type: "trailing", min_days: 3 }],
         funded: { daily_loss_pct: 4, max_loss_pct: 6, max_loss_type: "trailing", profit_split: 80 } },
  blank: { name: "Blank", phases: [{ name: "Phase 1", target_pct: "", daily_loss_pct: "", max_loss_pct: "", max_loss_type: "static", min_days: 0 }],
           funded: { daily_loss_pct: "", max_loss_pct: "", max_loss_type: "static", profit_split: "" } },
};

// ---------- view switch: Home (accounts + journal) / Trade (the chart dashboard) ----------
function setView(v) {
  document.body.classList.toggle("view-home", v === "home");
  for (const b of document.querySelectorAll("#viewSeg button")) b.classList.toggle("on", b.dataset.view === v);
  lsSet("view", v);
  if (v === "home") { J.acc ? openAccount(J.acc.id) : loadHome(); }
  else window.dispatchEvent(new Event("resize"));
}
$("viewSeg").addEventListener("click", e => { const b = e.target.closest("[data-view]"); if (b) { if (b.dataset.view === "home") J.acc = null; setView(b.dataset.view); } });

// ---------- Home ----------
async function loadHome() {
  try { J.accounts = (await jApi(`/api/journal/accounts${J.archived ? "?archived=true" : ""}`)).accounts; } catch { J.accounts = []; }
  renderHome();
  demoLoad();
}
function bar(pct, cls = "") { return `<div class="jbar ${cls}"><span style="width:${Math.max(0, Math.min(100, pct))}%"></span></div>`; }
function meters(c) {
  const out = [];
  if (c.target_amt != null) out.push(`<div class="jm"><div class="jmh"><span>Profit target</span><b class="${jCls(c.profit)}">${jUsd(c.profit)} <span class="meta">of ${jMoney(c.target_amt)}</span></b></div>
      ${bar(100 * c.profit / c.target_amt, "tgt")}</div>`);
  else out.push(`<div class="jm"><div class="jmh"><span>Profit so far</span><b class="${jCls(c.profit)}">${jUsd(c.profit)}</b></div></div>`);
  if (c.daily_limit != null) out.push(`<div class="jm"><div class="jmh"><span>Today's loss room</span><b>${jMoney(c.daily_room)} <span class="meta">of ${jMoney(c.daily_limit)}</span></b></div>
      ${bar(100 * c.daily_room / c.daily_limit, c.daily_room < c.daily_limit * 0.35 ? "warnb" : "room")}</div>`);
  if (c.max_room != null) {
    const full = Math.max(1, c.rules.max_loss_pct / 100 * (c._size || 0));          // the whole max-loss allowance in $
    out.push(`<div class="jm"><div class="jmh"><span>Max loss room</span><b>${jMoney(c.max_room)} <span class="meta">above ${jMoney(c.max_floor)}</span></b></div>
      ${bar(100 * c.max_room / full, c.max_room < 0.35 * full ? "warnb" : "room")}</div>`);
  }
  return out.join("");
}
function phaseLabel(a, p) { return p.is_funded ? "Funded" : `${esc(p.name)} of ${a.total_phases}`; }
function stepper(a, sel) {
  const names = [...a.rules.phases.map(p => p.name), "Funded"];
  return `<div class="jstep">${names.map((n, i) => { const p = a.phases.find(x => x.idx === i);
    const st = !p ? "todo" : p.result === "passed" ? "done" : p.result === "failed" ? "fail" : "now";
    return `<button class="${st} ${sel && p && sel.id === p.id ? "sel" : ""}" ${p ? `data-ph="${p.id}"` : "disabled"}>
      <i>${st === "done" ? "✓" : st === "fail" ? "✕" : i + 1}</i><span>${esc(n)}</span></button>`; }).join('<span class="jline"></span>')}</div>`;
}
function renderHome() {
  const el = $("homeView"); if (!el) return;
  const act = J.accounts.filter(a => !a.archived && a.id !== (J.demo && J.demo.journal_account));
  const funded = act.filter(a => a.current && a.current.is_funded && !a.current.result).length;
  const today = act.reduce((s, a) => s + (a.current ? a.current.check.today_pnl : 0), 0);
  const demoId = J.demo && J.demo.journal_account;
  const cards = J.accounts.filter(a => a.id !== demoId).map(a => { const p = a.current, c = p.check; c._size = a.size; const [sc, st] = STATUS[c.status] || ["NA", c.status];
    return `<div class="acard ${a.archived ? "arch" : ""}" data-acc="${a.id}" tabindex="0" role="button" aria-label="Open ${esc(a.name)}">
      <div class="ahd"><div><b>${esc(a.name)}</b><div class="meta">${esc(a.firm || "")}${a.firm ? " · " : ""}${jMoney(a.size)} account</div></div>
        <span class="bias ${sc}">${st}</span></div>
      <div class="aphase"><span class="chip">${phaseLabel(a, p)}</span><span class="meta">balance <b>${jMoney(c.balance)}</b></span></div>
      ${c.breach ? `<div class="jbreach">${esc(c.breach.text)}</div>` : ""}
      ${meters(c)}
      <div class="meta afoot">${a.n_trades} trades · ${c.days_traded}${c.min_days ? ` of ${c.min_days}` : ""} trading days · last ${a.last_trade_at ? jDay(a.last_trade_at) : "none yet"}</div>
    </div>`; }).join("");
  const plan = agentState.data && agentState.data.chief && agentState.data.chief.plan;
  el.innerHTML = `<div class="hwrap">
    <div class="hhead"><div><h2>My accounts</h2><div class="meta">Prop-firm challenges and funded accounts · phase-wise trading journal</div></div>
      <div class="hbtns"><button data-j="records">All records</button><button class="primary" data-j="new">＋ New account</button></div></div>
    <div class="stats hsum">
      <div class="stat"><div class="v">${act.length}</div><div class="k">active accounts</div></div>
      <div class="stat"><div class="v">${funded}</div><div class="k">funded</div></div>
      <div class="stat"><div class="v ${jCls(today)}">${jUsd(Math.round(today * 100) / 100)}</div><div class="k">today, all accounts</div></div>
      <div class="stat"><div class="v">${act.reduce((s, a) => s + a.n_trades, 0)}</div><div class="k">trades logged</div></div></div>
    <div class="tstrip" id="todayStrip">${todayHtml()}</div>
    <div class="hgrid">
      <div class="acards"><div class="acard demoacard" id="demoAcard" data-demo-journal role="button" tabindex="0" aria-label="Open the AuEdge demo account's journal">${demoCardHtml()}</div>
        ${cards || `<div class="acard empty" data-j="new" role="button" tabindex="0"><b>＋ Add your prop-firm account</b>
        <div class="meta">Enter your firm's rules: profit target, daily loss, max loss and minimum days for each phase. AuEdge tracks them for every trade you log.</div></div>`}</div>
      <aside class="hside">
        <div class="card"><div class="sect">Tips</div><ul class="btlines">
          <li>Log every trade, wins and losses, with how you felt and whether you followed your plan.</li>
          <li>Check <b>today's loss room</b> before each trade; never risk more than what's left.</li>
          <li>The journal checks closed trades only. Your firm also counts open (floating) losses, so leave a buffer.</li></ul></div>
        <button class="linkbtn" data-j="archived">${J.archived ? "Hide archived accounts" : "Show archived accounts"}</button>
      </aside></div></div>`;
}

// ---------- AuEdge's own demo account (Demo tab): shown on Home and in the top-bar pill ----------
J.demo = null;
async function demoLoad() {
  try { J.demo = await jApi("/api/demo"); } catch { return; }
  demoPill();
  if ($("todayStrip")) $("todayStrip").innerHTML = todayHtml();
  if ($("demoAcard")) $("demoAcard").innerHTML = demoCardHtml();
}
demoLoad(); setInterval(demoLoad, 30000);
const DEMO_DAY_LOSS = 350, DEMO_DAY_PROFIT = 150;          // the demo account's daily limits (Discipline coach)
function demoCardHtml() {
  const dm = J.demo;
  if (!dm) return `<div class="ahd"><div><b>AuEdge Demo</b><div class="meta">Automatic · loading…</div></div></div>`;
  const pnl = Math.round((dm.equity - dm.start) * 100) / 100, op = dm.open || [];
  const fl = op.reduce((a2, t) => a2 + (t.unrealised || 0), 0);
  const room = Math.max(0, DEMO_DAY_LOSS + Math.min(0, dm.today));
  const last = (dm.closed || []).length ? dm.closed[dm.closed.length - 1] : null;
  const status = op.length ? ["BUY", "Trade open"] : dm.today <= -DEMO_DAY_LOSS ? ["SELL", "Day stopped (loss limit)"]
    : dm.today >= DEMO_DAY_PROFIT ? ["BUY", "Day done (+$150 target)"] : ["NA", "Waiting for a call"];
  return `<div class="ahd"><div><b>AuEdge Demo</b><div class="meta">Automatic demo trading · ${jMoney(dm.start)} account · ${dm.lot} lot</div></div>
      <span class="bias ${status[0]}">${status[1]}</span></div>
    <div class="aphase"><span class="chip">AuEdge's own calls</span><span class="meta">balance <b>${jMoney(dm.balance)}</b></span></div>
    <div class="jm"><div class="jmh"><span>Profit since start</span><b class="${jCls(pnl)}">${jUsd(pnl)}</b></div></div>
    ${op.length ? `<div class="jm"><div class="jmh"><span>Open ${op[0].side} ${op[0].lot}</span><b class="${jCls(fl)}">${jUsd(Math.round(fl * 100) / 100)}</b></div></div>` : ""}
    <div class="jm"><div class="jmh"><span>Today's loss room</span><b>${jMoney(room)} <span class="meta">of ${jMoney(DEMO_DAY_LOSS)}</span></b></div>
      ${bar(100 * room / DEMO_DAY_LOSS, room < DEMO_DAY_LOSS * 0.35 ? "warnb" : "room")}</div>
    <div class="jm"><div class="jmh"><span>Today · this week</span><b><span class="${jCls(dm.today)}">${jUsd(dm.today)}</span> · <span class="${jCls(dm.week)}">${jUsd(dm.week)}</span></b></div></div>
    <div class="meta afoot">${dm.trades} closed trades${dm.win_rate != null ? ` · ${dm.win_rate}% won` : ""} · last ${last ? jDay(last.closed_ts) : "none yet"} · tap for its journal</div>`;
}
function openDemoTab() { J.acc = null; setView("home"); showHomePage("demo"); }
function demoPill() {
  const el = $("demoPill"), dm = J.demo;
  if (!dm) { el.hidden = true; return; }
  const op = (dm.open || []).length, fl = (dm.open || []).reduce((a2, t) => a2 + (t.unrealised || 0), 0);
  el.hidden = false;
  $("demoPillTxt").innerHTML = `<b>DEMO</b><span class="det"> · today <span class="${jCls(dm.today)}">${jUsd(dm.today)}</span>${op ? ` · ${op} open` : ""}</span>`;
  el.title = `AuEdge demo account · balance ${jMoney(dm.balance)} · today ${jUsd(dm.today)}${op ? ` · ${op} open ${jUsd(Math.round(fl * 100) / 100)}` : " · no open trade"} · click to open the Demo tab`;
}
$("demoPill").addEventListener("click", openDemoTab);
function openDemoJournal() {
  const id = J.demo && J.demo.journal_account;
  if (!id) return openDemoTab();
  J.page = "account"; J.calMonth = null; J.calDay = null; J.phaseSel = null;
  if (!document.body.classList.contains("view-home")) setView("home");
  openAccount(id);
}
document.addEventListener("click", e => { if (e.target.closest("[data-demo-journal]")) openDemoJournal(); });
document.addEventListener("click", e => { if (e.target.closest("[data-demo-open]")) openDemoTab(); });

// ---------- Today strip (Home): AuEdge's call, the demo position, today's result, next big news ----------
J.news = null;
async function jLoadNews() { try { J.news = (await jApi("/api/news")).events; } catch { J.news = null; } if ($("todayStrip")) $("todayStrip").innerHTML = todayHtml(); }
jLoadNews(); setInterval(jLoadNews, 10 * 60000);
function nextIn() { const n = agentState.nextAt; if (!n) return "—"; const s = Math.max(0, Math.round((n - Date.now()) / 1000)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; }
setInterval(() => { if ($("tdNext")) $("tdNext").textContent = nextIn(); }, 1000);
function todayHtml() {
  const d = agentState.data, c = d && d.chief, plan = c && c.plan;
  const call = !c ? `<div class="meta">Loading the analysis…</div>` : `<div class="trow"><span class="bias ${plan.kind === "now" ? plan.side : plan.kind === "watch" ? "NA" : "WAIT"}">${esc(plan.action)}</span>
      <span class="meta">confidence ${c.confidence}% · next in <b id="tdNext">${nextIn()}</b></span></div>
    ${plan.kind === "now" ? `<div class="meta">Entry ${fmt((plan.entry_lo + plan.entry_hi) / 2)} · stop ${fmt(plan.stop)} · half ${fmt(plan.be_at)} · target ${fmt(plan.t1)}</div>
      <button class="primary" data-jn-call>＋ Add to my journal</button>` : `<div class="meta clamp2">${esc(c.headline || "")}</div>`}
    <button data-view-go="trade">Chart dashboard →</button>`;
  const dm = J.demo;
  const dpos = (dm && dm.open) || [];
  const dflo = dpos.reduce((a2, t) => a2 + (t.unrealised || 0), 0);
  const demoCell = !dm ? `<div class="meta">Loading the demo account…</div>`
    : dpos.length ? `<div class="trow"><span class="bias ${dpos[0].side}">${dpos[0].side}</span><b>${dpos[0].lot} lot</b>
        <span class="tv ${jCls(dflo)}" style="margin-left:auto">${jUsd(Math.round(dflo * 100) / 100)}</span></div>
      <div class="meta">Entry ${fmt(dpos[0].entry)} · stop ${fmt(dpos[0].stop_now ?? dpos[0].stop)}${dpos[0].half ? " (breakeven)" : ""} · half ${fmt(dpos[0].be)} · target ${fmt(dpos[0].t1)}</div>
      <button data-demo-open>Open the Demo tab →</button>`
    : `<div class="tv" style="font-size:15px">No open trade</div><div class="meta">Balance ${jMoney(dm.balance)} · ${dm.trades} closed trade(s) ·
        waiting for the next BUY / SELL NOW call.</div><button data-demo-open>Open the Demo tab →</button>`;
  const jToday = J.accounts.filter(a2 => !a2.archived && a2.current).reduce((s2, a2) => s2 + a2.current.check.today_pnl, 0);
  const now = Date.now() / 1000, ev = (J.news || []).find(e2 => e2.t > now && e2.impact === "High");
  const evIn = ev ? ev.t - now : 0;
  return `<div class="tcell"><div class="k">AuEdge call</div>${call}</div>
    <div class="tcell"><div class="k">AuEdge demo position</div>${demoCell}</div>
    <div class="tcell"><div class="k">Today</div>
      ${dm ? `<div class="tv ${jCls(dm.today)}">${jUsd(dm.today)}</div><div class="meta">AuEdge demo · this week ${jUsd(dm.week)}</div>` : ""}
      <div class="meta" style="margin-top:4px">Journal accounts <b class="${jCls(jToday)}">${jUsd(Math.round(jToday * 100) / 100)}</b></div></div>
    <div class="tcell"><div class="k">Next big news</div>${ev ? `<div class="trow"><b>${esc(ev.name)}</b></div>
      <div class="meta">${new Date(ev.t * 1000).toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" })} ·
        in ${evIn > 86400 ? Math.round(evIn / 86400) + " day(s)" : Math.floor(evIn / 3600) + "h " + Math.floor(evIn % 3600 / 60) + "m"}
        ${ev.blocks ? " · no new trades around it" : ""}</div>` : `<div class="meta">No high-impact US news coming up.</div>`}</div>`;
}

// ---------- Account page ----------
async function openAccount(id, phaseId) {
  const a = await jApi(`/api/journal/accounts/${id}`);
  if (a.error) { J.acc = null; return loadHome(); }
  J.acc = a; J.phaseSel = phaseId ? a.phases.find(p => p.id === phaseId) : (J.phaseSel && J.phaseSel.account_id === a.id ? a.phases.find(p => p.id === J.phaseSel.id) : null) || a.current;
  renderAccount();
}
function rulesText(r) {
  return [r.target_pct != null ? `Target <b>${r.target_pct}%</b>` : "No target", r.daily_loss_pct ? `Daily loss <b>${r.daily_loss_pct}%</b>` : "",
          r.max_loss_pct ? `Max loss <b>${r.max_loss_pct}%</b> (${r.max_loss_type})` : "", r.min_days ? `Min <b>${r.min_days}</b> trading days` : "",
          r.consistency_pct ? `Best day ≤ <b>${r.consistency_pct}%</b> of profit` : "",
          r.profit_split ? `Profit split <b>${r.profit_split}%</b>` : ""].filter(Boolean).join(" · ");
}
function renderAccount() {
  const a = J.acc, p = J.phaseSel, c = p.check, s = c.stats; c._size = a.size;
  const [sc, st] = STATUS[c.status] || ["NA", c.status];
  const isCur = !p.result, last = a.phases[a.phases.length - 1];
  const trades = a.trades.filter(t => t.phase_id === p.id);
  const stat = (v, k, cl = "") => `<div class="stat"><div class="v ${cl}">${v}</div><div class="k">${k}</div></div>`;
  const nextName = p.is_funded ? "" : (a.rules.phases[p.idx + 1] ? a.rules.phases[p.idx + 1].name : "Funded");
  const rows = trades.map(t => `<tr class="tclick" data-trade="${t.id}" title="Open this trade">
      <td>${jDate(t.opened_at)}</td><td><span class="bias ${t.side}">${t.side}</span>${t.source === "auedge" ? ' <span class="chip sm" title="From an AuEdge call">AuEdge</span>' : ""}</td>
      <td class="p">${t.lots ?? "—"}</td><td class="p">${fmt(t.entry)} → ${t.exit != null ? fmt(t.exit) : t.net == null ? "open" : "—"}</td>
      <td class="meta">${esc(t.setup || "")}</td><td>${t.followed_plan == null ? "" : t.followed_plan ? "✓" : '<span class="dn">✕</span>'}</td>
      <td class="meta">${esc(t.emotion || "")}</td><td class="p meta">${t.planned_rr != null ? "1:" + t.planned_rr : ""}</td><td class="p">${t.r != null ? (t.r > 0 ? "+" : "") + t.r + "R" : ""}</td>
      <td class="p ${jCls(t.net)}" style="text-align:right">${t.net == null ? "open" : jUsd(t.net)}</td></tr>`).join("");
  const maxDay = Math.max(1, ...c.days.map(d => Math.abs(d.pnl)));
  $("homeView").innerHTML = `<div class="hwrap">
    <div class="hhead"><div><button class="linkbtn" data-j="back">← All accounts</button>
        <h2>${esc(a.name)} <span class="bias ${sc}">${st}</span></h2>
        <div class="meta">${esc(a.firm || "")}${a.firm ? " · " : ""}${jMoney(a.size)} account · created ${jDay(a.created_at)}${a.archived ? " · archived" : ""}</div></div>
      <div class="hbtns">${J.demo && J.demo.journal_account === a.id ? `<button class="primary" data-demo-open>Live Demo tab →</button>`
          : `<button class="primary" data-j="trade">＋ Add trade</button>`}<button data-j="edit">Edit account</button>
        <button data-j="archive">${a.archived ? "Unarchive" : "Archive"}</button></div></div>
    ${stepper(a, p)}
    <div class="hgrid">
      <div>
        <div class="card jpanel"><div class="sect">${p.is_funded ? "Funded account" : esc(p.name)} · started ${jDay(p.started_at)}${p.ended_at ? ` · ended ${jDay(p.ended_at)}` : ""}</div>
          <div class="meta" style="margin-bottom:8px">${rulesText(c.rules)} · starting balance ${jMoney(p.start_balance)}</div>
          ${c.breach ? `<div class="jbreach">⚠ ${esc(c.breach.text)}. Check with your firm; most firms end the phase here.</div>` : ""}
          ${c.status === "need_days" ? `<div class="jok">Target reached. Trade on at least ${c.min_days - c.days_traded} more day(s) to meet the minimum (small, safe trades).</div>` : ""}
          ${c.status === "target_reached" && isCur ? `<div class="jok">🎉 Target reached and minimum days met. Mark it passed once your firm confirms.</div>` : ""}
          ${c.status === "need_consistency" ? `<div class="jbreach" style="background:var(--warn-bg);color:var(--warn)">Target reached, but your best day is ${c.consistency.best_day_share}% of the profit
            (limit ${c.consistency.limit_pct}%). About ${jMoney(c.consistency.profit_needed)} more profit, without another big day, brings it within the rule.</div>` : ""}
          <div class="jbig"><div><div class="k">Balance</div><div class="big">${jMoney(c.balance)}</div></div>
            <div><div class="k">Profit this phase</div><div class="big ${jCls(c.profit)}">${jUsd(c.profit)}</div></div>
            ${c.target_left != null ? `<div><div class="k">Left to target</div><div class="big">${jMoney(c.target_left)}</div></div>` : ""}
            <div><div class="k">Trading days</div><div class="big">${c.days_traded}${c.min_days ? `<span class="meta"> / ${c.min_days}</span>` : ""}</div></div></div>
          ${meters(c)}
          <div class="frm">${isCur ? `${!p.is_funded ? `<button class="${c.status === "target_reached" ? "primary" : ""}" data-j="pass" ${c.status === "breached" ? "disabled" : ""}>Mark ${esc(p.name)} passed → start ${esc(nextName)}</button>` : ""}
              <button data-j="fail">Mark ${p.is_funded ? "account" : "phase"} failed</button>` : ""}
            ${p.id === last.id && p.result || (last.id !== p.id && last.idx === p.idx + 1 && !last.result) ? `<button data-j="reopen">Undo ${p.result || "last"} mark</button>` : ""}</div>
          ${p.note ? `<div class="meta">Note: ${esc(p.note)}</div>` : ""}</div>
        <div class="seg jsub">${[["journal", "Journal"], ["calendar", "Calendar"], ["rr", "Risk : Reward"], ["consistency", "Consistency"]]
            .map(([k, l]) => `<button data-sub="${k}" class="${J.sub === k ? "on" : ""}">${l}</button>`).join("")}</div>
        ${J.sub === "calendar" ? `<div class="card"><div class="sect">Calendar · ${esc(p.is_funded ? "Funded" : p.name)} · your firm's trading days</div>
            ${jCalendar(Object.fromEntries(c.days.map(d => [d.day, d])), trades)}</div>`
          : J.sub === "rr" ? rrCard(c.rr)
          : J.sub === "consistency" ? consistencyCard(c, a)
          : `<div class="card"><div class="sect">Journal · ${esc(p.is_funded ? "Funded" : p.name)} · newest first · click a trade to open it</div>
          ${rows ? `<div class="jtable"><table class="lvtable"><tr class="meta"><td>Opened</td><td>Side</td><td>Lots</td><td>Entry → exit</td><td>Setup</td><td>Plan</td><td>Mood</td><td>R:R plan</td><td>R</td><td style="text-align:right">Net</td></tr>${rows}</table></div>${jCards(trades, false)}`
            : `<div class="meta">No trades in this phase yet. <button class="linkbtn" data-j="trade">Add your first trade</button></div>`}</div>`}
      </div>
      <aside>
        <div class="card"><div class="sect">Stats · this phase</div>
          <div class="stats two">${stat(s.n, "closed trades")}${stat(s.win_rate != null ? s.win_rate + "%" : "—", "win rate")}
            ${stat(jUsd(s.avg_win), "average win", "up")}${stat(jUsd(s.avg_loss), "average loss", "dn")}
            ${stat(s.profit_factor ?? "—", "profit factor")}${stat(s.avg_r != null ? s.avg_r + "R" : "—", "average R")}
            ${stat(jUsd(s.best), "best", jCls(s.best))}${stat(jUsd(s.worst), "worst", jCls(s.worst))}</div>
          ${s.followed_plan_pct != null ? `<div class="meta" style="margin-top:8px">Followed the plan in <b>${s.followed_plan_pct}%</b> of trades:
            plan trades ${jUsd(s.followed_pnl)}, off-plan trades <span class="${jCls(s.broke_pnl)}">${jUsd(s.broke_pnl)}</span>.</div>` : ""}
          ${c.equity.length ? equitySvg(c.equity, "$") : ""}</div>
        ${c.days.length ? `<div class="card"><div class="sect">Day by day</div>${c.days.slice(-14).reverse().map(d => `<div class="jday"><span>${esc(d.day)}</span>
            <span class="dbar"><i class="${d.pnl >= 0 ? "pos" : "neg"}" style="width:${Math.round(100 * Math.abs(d.pnl) / maxDay)}%"></i></span><b class="${jCls(d.pnl)}">${jUsd(d.pnl)}</b></div>`).join("")}</div>` : ""}
        ${s.by_setup.length ? `<div class="card"><div class="sect">By setup</div><table class="lvtable">${s.by_setup.map(x => `<tr><td>${esc(x.setup)}</td><td class="d">${x.n}</td>
            <td class="d">${x.win_rate}%</td><td class="p ${jCls(x.pnl)}" style="text-align:right">${jUsd(x.pnl)}</td></tr>`).join("")}</table></div>` : ""}
        ${s.by_emotion.length ? `<div class="card"><div class="sect">By mood</div><table class="lvtable">${s.by_emotion.map(x => `<tr><td>${esc(x.emotion)}</td><td class="d">${x.n}</td>
            <td class="p ${jCls(x.pnl)}" style="text-align:right">${jUsd(x.pnl)}</td></tr>`).join("")}</table></div>` : ""}
        ${a.notes ? `<div class="card"><div class="sect">Account notes</div><div class="meta" style="white-space:pre-wrap">${esc(a.notes)}</div></div>` : ""}
      </aside></div></div>`;
  $("homeView").scrollTop = 0;
}

// ---------- Calendar (month grid by trading day; tap a day to see its trades) ----------
function jCalendar(days, trades, showAcc = false) {
  const keys = Object.keys(days).sort();
  if (!J.calMonth) { const d = keys.length ? new Date(keys[keys.length - 1] + "T12:00:00") : new Date(); J.calMonth = new Date(d.getFullYear(), d.getMonth(), 1); }
  const m = J.calMonth, first = new Date(m.getFullYear(), m.getMonth(), 1), lead = (first.getDay() + 6) % 7;
  const nDays = new Date(m.getFullYear(), m.getMonth() + 1, 0).getDate(), ym = `${m.getFullYear()}-${String(m.getMonth() + 1).padStart(2, "0")}`;
  let cells = "", mPnl = 0, mWin = 0, mLoss = 0;
  for (let i = 0; i < lead; i++) cells += `<div class="cday empty"></div>`;
  for (let dd = 1; dd <= nDays; dd++) {
    const k = `${ym}-${String(dd).padStart(2, "0")}`, d = days[k];
    if (d) { mPnl += d.pnl; d.pnl > 0 ? mWin++ : d.pnl < 0 && mLoss++; }
    cells += `<button class="cday ${!d ? "" : d.pnl > 0 ? "pos" : d.pnl < 0 ? "neg" : "flat"} ${J.calDay === k ? "sel" : ""}" data-jday="${k}" ${d ? "" : "disabled"}>
      <span class="dn">${dd}</span>${d ? `<span class="pl">${jUsd(Math.round(d.pnl))}</span><span class="tg">${d.n || ""}T</span>` : ""}</button>`;
  }
  // weekly totals on the right of each row
  const dayTrades = J.calDay ? trades.filter(t => t.day === J.calDay) : [];
  return `<div class="calhead"><button data-jcal="-1" aria-label="Previous month">‹</button>
      <b>${m.toLocaleDateString(undefined, { month: "long", year: "numeric" })}</b>
      <span class="${jCls(mPnl)}">${jUsd(Math.round(mPnl * 100) / 100)}</span><button data-jcal="1" aria-label="Next month">›</button></div>
    <div class="meta" style="margin:-4px 0 6px">${mWin} green day(s) · ${mLoss} red day(s) this month</div>
    <div class="calgrid">${["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map(w => `<div class="cwk">${w}</div>`).join("")}${cells}</div>
    ${J.calDay ? `<div class="sect" style="margin-top:12px">${new Date(J.calDay + "T12:00:00").toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}</div>
      ${dayTrades.length ? `<div class="jtable"><table class="lvtable">${dayTrades.map(t => tradeRow(t, showAcc)).join("")}</table></div>${jCards(dayTrades, showAcc)}` : `<div class="meta">No trades.</div>`}`
      : `<div class="meta" style="margin-top:6px">Tap a day to see its trades.</div>`}`;
}
function tradeCard(t, showAcc) {
  return `<div class="tcard tclick" data-trade="${t.id}" data-tacc="${t.account_id}" role="button" tabindex="0">
    <div class="tc1"><span class="bias ${t.side}">${t.side}</span><b>${t.lots ?? "—"} lot</b><span class="meta">${jDate(t.opened_at)}</span>
      <b class="net ${jCls(t.net)}">${t.net == null ? "open" : jUsd(t.net)}</b></div>
    <div class="tc2 meta">${showAcc ? `<b>${esc(t.account)}</b> · ${esc(t.phase || "")} · ` : ""}${fmt(t.entry)} → ${t.exit != null ? fmt(t.exit) : "—"}
      ${t.setup ? " · " + esc(t.setup) : ""}${t.planned_rr != null ? " · R:R 1:" + t.planned_rr : ""}${t.r != null ? ` · ${t.r > 0 ? "+" : ""}${t.r}R` : ""}
      ${t.followed_plan === 0 ? ' · <span class="dn">off plan</span>' : ""}${t.emotion ? " · " + esc(t.emotion) : ""}${t.source === "auedge" ? ' · <span class="chip sm">AuEdge</span>' : ""}</div></div>`;
}
const jCards = (ts, showAcc) => `<div class="jcards">${ts.map(t => tradeCard(t, showAcc)).join("")}</div>`;
function tradeRow(t, showAcc) {
  return `<tr class="tclick" data-trade="${t.id}" data-tacc="${t.account_id}" title="Open this trade">
    <td>${jDate(t.opened_at)}</td>${showAcc ? `<td><b>${esc(t.account)}</b><div class="meta">${esc(t.phase || "")}</div></td>` : ""}
    <td><span class="bias ${t.side}">${t.side}</span></td><td class="p">${t.lots ?? "—"}</td>
    <td class="p">${fmt(t.entry)} → ${t.exit != null ? fmt(t.exit) : t.net == null ? "open" : "—"}</td><td class="meta">${esc(t.setup || "")}</td>
    <td class="p meta">${t.planned_rr != null ? "1:" + t.planned_rr : ""}</td><td class="p">${t.r != null ? (t.r > 0 ? "+" : "") + t.r + "R" : ""}</td>
    <td class="p ${jCls(t.net)}" style="text-align:right">${t.net == null ? "open" : jUsd(t.net)}</td></tr>`;
}
function rrCard(rr) {
  const st = (v, k, cl = "") => `<div class="stat"><div class="v ${cl}">${v}</div><div class="k">${k}</div></div>`;
  const maxN = Math.max(1, ...rr.dist.map(d => d.n));
  const edge = rr.win_rate != null && rr.breakeven_win_rate != null ? rr.win_rate - rr.breakeven_win_rate : null;
  return `<div class="card"><div class="sect">Risk : Reward · this phase</div>
    ${rr.n_with_stop ? `<div class="stats">${st(rr.avg_planned != null ? "1 : " + rr.avg_planned : "—", "average planned R:R")}
        ${st(rr.avg_achieved != null ? (rr.avg_achieved > 0 ? "+" : "") + rr.avg_achieved + "R" : "—", "average result per trade", jCls(rr.avg_achieved))}
        ${st(rr.avg_win_r != null ? "+" + rr.avg_win_r + "R" : "—", "average win", "up")}${st(rr.avg_loss_r != null ? rr.avg_loss_r + "R" : "—", "average loss", "dn")}</div>
      <div class="stats" style="margin-top:6px">${st(rr.win_rate != null ? rr.win_rate + "%" : "—", "your win rate")}
        ${st(rr.breakeven_win_rate != null ? rr.breakeven_win_rate + "%" : "—", "win rate needed to break even")}
        ${st(jUsd(rr.expectancy_usd), "expectancy per trade", jCls(rr.expectancy_usd))}
        ${st(rr.with_target ? `${rr.hit_target}/${rr.with_target}` : "—", "reached the target")}</div>
      ${edge != null ? `<div class="${edge >= 0 ? "jok" : "jbreach"}" style="margin-top:8px">${edge >= 0
          ? `Your win rate is ${edge} points above what your average R:R needs. That's a real edge if it holds over more trades.`
          : `Your win rate is ${-edge} points below what your average R:R needs. Aim for bigger targets or better entries.`}</div>` : ""}
      <div class="sect" style="margin-top:12px">Results in R (1R = what you lose at the stop)</div>
      ${rr.dist.map(d => `<div class="jday"><span>${esc(d.label)}</span><span class="dbar"><i class="${/−/.test(d.label) ? "neg" : "pos"}" style="width:${Math.round(100 * d.n / maxN)}%"></i></span><b>${d.n}</b></div>`).join("")}
      ${rr.n_without_stop ? `<div class="meta" style="margin-top:6px">${rr.n_without_stop} trade(s) have no stop or lots recorded, so they can't be measured in R.</div>` : ""}`
    : `<div class="meta">Record entry, stop, target and lots on your trades to see planned vs achieved risk:reward.</div>`}
    <div class="meta" style="margin-top:8px">Planned R:R = target distance ÷ stop distance when you entered. Achieved R = your real result ÷ the money at risk.
      Win rate needed = 1 ÷ (1 + R:R).</div></div>`;
}
function consistencyCard(c, a) {
  const k = c.consistency, st = (v, l, cl = "") => `<div class="stat"><div class="v ${cl}">${v}</div><div class="k">${l}</div></div>`;
  const maxDay = Math.max(1, ...c.days.map(d => Math.abs(d.pnl)));
  const lim = k.limit_pct, share = k.best_day_share;
  return `<div class="card"><div class="sect">Consistency · this phase</div>
    ${share != null ? `<div class="jm"><div class="jmh"><span>Best day as % of total profit${lim ? ` (your firm's limit ${lim}%)` : ""}</span>
        <b class="${lim && share > lim ? "dn" : "up"}">${share}%</b></div>${bar(share, lim && share > lim ? "warnb" : "tgt")}
        ${lim ? `<div class="jlim" style="left:${Math.min(100, lim)}%"></div>` : ""}</div>
      <div class="${lim ? (k.ok ? "jok" : "jbreach") : "meta"}" style="margin-top:8px">${lim ? (k.ok ? `Within the rule: your best day (${k.best_day.day}, ${jUsd(k.best_day.pnl)}) is ${share}% of the profit.`
          : `Breaks the rule: best day ${jUsd(k.best_day.pnl)} on ${k.best_day.day} is ${share}% of the profit. About ${jMoney(k.profit_needed)} more profit (spread over other days) fixes it.`)
          : `Best day ${jUsd(k.best_day.pnl)} on ${k.best_day.day}. Add your firm's consistency % in <b>Edit account</b> to check it automatically.`}</div>`
      : `<div class="meta">Shown once this phase is in profit.</div>`}
    <div class="stats" style="margin-top:10px">${st(`${k.win_days} / ${k.loss_days}`, "green / red days")}
      ${st(jUsd(k.avg_win_day), "average green day", "up")}${st(jUsd(k.avg_loss_day), "average red day", "dn")}${st(jUsd(k.worst_day), "worst day", jCls(k.worst_day))}</div>
    <div class="stats" style="margin-top:6px">${st(k.avg_lots ?? "—", "average lots")}${st(k.min_lots != null ? `${k.min_lots} – ${k.max_lots}` : "—", "smallest – biggest lots")}
      ${st(k.lot_spread != null ? "×" + k.lot_spread : "—", "biggest vs average lot", k.lot_spread > 2 ? "dn" : "")}
      ${st(k.biggest_trade_share != null ? k.biggest_trade_share + "%" : "—", "biggest trade % of profit", k.biggest_trade_share > 50 ? "dn" : "")}</div>
    ${k.lot_spread > 2 ? `<div class="jbreach" style="background:var(--warn-bg);color:var(--warn);margin-top:8px">Your biggest lot is more than 2× your average. Many firms flag uneven lot sizes; keep size steady.</div>` : ""}
    ${c.days.length ? `<div class="sect" style="margin-top:12px">Daily results</div>${c.days.slice(-20).reverse().map(d => `<div class="jday"><span>${esc(d.day)}</span>
        <span class="dbar"><i class="${d.pnl >= 0 ? "pos" : "neg"}" style="width:${Math.round(100 * Math.abs(d.pnl) / maxDay)}%"></i></span><b class="${jCls(d.pnl)}">${jUsd(d.pnl)}</b></div>`).join("")}` : ""}
    <div class="meta" style="margin-top:8px">Firms use consistency rules so one lucky day can't pass a challenge or a payout. Steady lots and many small green days look best.</div></div>`;
}

// ---------- All records: every trade, every account ----------
async function openRecords() {
  J.page = "records"; J.acc = null; J.calMonth = null; J.calDay = null;
  try { J.rec.trades = (await jApi("/api/journal/trades")).trades; } catch { J.rec.trades = []; }
  if (!J.accounts.length) J.accounts = (await jApi("/api/journal/accounts")).accounts;
  renderRecords();
}
function recFiltered() {
  const f = J.rec.f;
  return J.rec.trades.filter(t => (!f.acc || t.account_id === +f.acc) && (!f.phase || t.phase === f.phase) && (!f.side || t.side === f.side)
    && (!f.setup || (t.setup || "") === f.setup) && (!f.res || (f.res === "win" ? t.net > 0 : f.res === "loss" ? t.net < 0 : t.net == null))
    && (!f.from || t.day >= f.from) && (!f.to || t.day <= f.to)
    && (!f.q || `${t.notes} ${t.mistakes} ${t.setup} ${t.emotion}`.toLowerCase().includes(f.q.toLowerCase())));
}
function renderRecords() {
  const all = J.rec.trades, f = J.rec.f, rows = recFiltered(), closed = rows.filter(t => t.net != null);
  const tot = closed.reduce((s, t) => s + t.net, 0), wins = closed.filter(t => t.net > 0), losses = closed.filter(t => t.net < 0);
  const rs = closed.filter(t => t.r != null).map(t => t.r);
  const opt = (vals, cur) => vals.map(([v, l]) => `<option value="${esc(v)}" ${String(cur ?? "") === String(v) ? "selected" : ""}>${esc(l)}</option>`).join("");
  const uniq = k => [...new Set(all.map(t => t[k]).filter(Boolean))].sort();
  const days = {}; for (const t of closed) { const d = days[t.day] || (days[t.day] = { pnl: 0, n: 0 }); d.pnl += t.net; d.n++; }
  const st = (v, k, cl = "") => `<div class="stat"><div class="v ${cl}">${v}</div><div class="k">${k}</div></div>`;
  $("homeView").innerHTML = `<div class="hwrap">
    <div class="hhead"><div><button class="linkbtn" data-j="back">← All accounts</button><h2>All records</h2>
        <div class="meta">Every trade in every account · ${all.length} in total</div></div>
      <div class="hbtns"><button class="primary" data-j="trade">＋ Add trade</button><button data-j="csv">Download CSV</button></div></div>
    <div class="card jfilters"><div class="frm">
      <label>Account <select data-rf="acc"><option value="">All</option>${opt(J.accounts.map(a => [a.id, a.name]), f.acc)}</select></label>
      <label>Phase <select data-rf="phase"><option value="">All</option>${opt(uniq("phase").map(x => [x, x]), f.phase)}</select></label>
      <label>Side <select data-rf="side"><option value="">Both</option>${opt([["BUY", "BUY"], ["SELL", "SELL"]], f.side)}</select></label>
      <label>Result <select data-rf="res"><option value="">All</option>${opt([["win", "Wins"], ["loss", "Losses"], ["open", "Open"]], f.res)}</select></label>
      <label>Setup <select data-rf="setup"><option value="">All</option>${opt(uniq("setup").map(x => [x, x]), f.setup)}</select></label>
      <label>From <input type="date" data-rf="from" value="${esc(f.from || "")}"></label><label>To <input type="date" data-rf="to" value="${esc(f.to || "")}"></label>
      <label>Search notes <input data-rf="q" value="${esc(f.q || "")}" placeholder="e.g. revenge" style="width:130px"></label>
      ${Object.values(f).some(Boolean) ? `<button class="linkbtn" data-j="clearf">Clear filters</button>` : ""}</div></div>
    <div class="stats" style="margin:12px 0">${st(rows.length, "trades shown")}${st(closed.length ? Math.round(100 * wins.length / closed.length) + "%" : "—", "win rate")}
      ${st(jUsd(Math.round(tot * 100) / 100), "net result", jCls(tot))}${st(losses.length && wins.length ? (wins.reduce((s, t) => s + t.net, 0) / -losses.reduce((s, t) => s + t.net, 0)).toFixed(2) : "—", "profit factor")}</div>
    <div class="seg jsub"><button data-j="rlist" class="${J.rec.cal ? "" : "on"}">List</button><button data-j="rcal" class="${J.rec.cal ? "on" : ""}">Calendar</button></div>
    <div class="card">${J.rec.cal ? jCalendar(days, rows, true)
      : rows.length ? `<div class="jtable"><table class="lvtable"><tr class="meta"><td>Opened</td><td>Account</td><td>Side</td><td>Lots</td><td>Entry → exit</td><td>Setup</td><td>R:R plan</td><td>R</td><td style="text-align:right">Net</td></tr>
          ${rows.map(t => tradeRow(t, true)).join("")}</table></div>${jCards(rows, true)}
          ${rs.length ? `<div class="meta" style="margin-top:6px">Average result ${(rs.reduce((a, b) => a + b, 0) / rs.length).toFixed(2)}R over ${rs.length} trades with a stop.</div>` : ""}`
      : `<div class="meta">No trades match.</div>`}</div></div>`;
}
function downloadCsv() {
  const cols = ["day", "opened_at", "closed_at", "account", "phase", "symbol", "side", "lots", "entry", "stop", "target", "exit", "pnl", "commission", "net",
                "planned_rr", "r", "setup", "emotion", "followed_plan", "rating", "source", "mistakes", "notes"];
  const iso = ts => ts ? new Date(ts * 1000).toISOString() : "";
  const cell = v => { const x = v == null ? "" : String(v); return /[",\n]/.test(x) ? `"${x.replace(/"/g, '""')}"` : x; };
  const lines = [cols.join(",")].concat(recFiltered().map(t => cols.map(c => cell(c.endsWith("_at") ? iso(t[c]) : t[c])).join(",")));
  const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
  const el = Object.assign(document.createElement("a"), { href: url, download: `auedge-journal-${new Date().toISOString().slice(0, 10)}.csv` });
  document.body.appendChild(el); el.click(); el.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000);
}

// ---------- New / edit account ----------
function phaseRow(p, i) {
  return `<div class="prow" data-i="${i}"><input class="pn" value="${esc(p.name)}" aria-label="Phase name">
    <label>Target % <input type="number" step="0.1" class="pt" value="${p.target_pct ?? ""}"></label>
    <label>Daily loss % <input type="number" step="0.1" class="pd" value="${p.daily_loss_pct ?? ""}"></label>
    <label>Max loss % <input type="number" step="0.1" class="pm" value="${p.max_loss_pct ?? ""}"></label>
    <label><select class="pty"><option value="static" ${p.max_loss_type !== "trailing" ? "selected" : ""}>static</option><option value="trailing" ${p.max_loss_type === "trailing" ? "selected" : ""}>trailing</option></select></label>
    <label>Min days <input type="number" step="1" class="pmd" value="${p.min_days ?? 0}"></label>
    <label title="Best single day may be at most this % of the total profit (leave empty if your firm has no such rule)">Consistency % <input type="number" step="1" class="pc" value="${p.consistency_pct ?? ""}" placeholder="none"></label>
    <button class="linkbtn" data-prm="${i}" aria-label="Remove phase">✕</button></div>`;
}
function accountForm(a) {
  const r = a ? a.rules : PRESETS.blank;
  $("modalBody").innerHTML = `<h2>${a ? "Edit account" : "New prop-firm account"}</h2>
    <div class="jform">
      <div class="frm"><label>Name <input id="jaName" value="${esc(a ? a.name : "")}" placeholder="e.g. 10K Challenge #1" style="width:200px"></label>
        <label>Firm <input id="jaFirm" value="${esc(a ? a.firm : "")}" placeholder="your prop firm" style="width:160px"></label>
        <label>Account size $ <input id="jaSize" type="number" step="1000" value="${a ? a.size : ""}" ${a ? "disabled" : ""} placeholder="10000" style="width:110px"></label></div>
      <div class="sect" style="margin-top:12px">Phases · your firm's rules (percent of the account size)</div>
      ${a ? "" : `<div class="frm"><span class="meta">Start from:</span><button data-preset="two">Common 2-step</button><button data-preset="one">1-step</button><button data-preset="blank">Blank</button></div>`}
      <div id="jaPhases">${r.phases.map(phaseRow).join("")}</div>
      <button class="linkbtn" data-j="addphase">＋ Add a phase</button>
      <div class="sect" style="margin-top:12px">Funded account rules</div>
      <div class="prow" id="jaFunded"><b style="min-width:70px">Funded</b>
        <label>Daily loss % <input type="number" step="0.1" class="pd" value="${r.funded.daily_loss_pct ?? ""}"></label>
        <label>Max loss % <input type="number" step="0.1" class="pm" value="${r.funded.max_loss_pct ?? ""}"></label>
        <label><select class="pty"><option value="static" ${r.funded.max_loss_type !== "trailing" ? "selected" : ""}>static</option><option value="trailing" ${r.funded.max_loss_type === "trailing" ? "selected" : ""}>trailing</option></select></label>
        <label>Profit split % <input type="number" step="1" class="ps" value="${r.funded.profit_split ?? ""}"></label>
        <label title="Best single day may be at most this % of the profit (for payouts)">Consistency % <input type="number" step="1" class="pc" value="${r.funded.consistency_pct ?? ""}" placeholder="none"></label></div>
      <div class="frm" style="margin-top:10px"><label>New day starts at <select id="jaReset">
          <option value="utc">00:00 UTC</option><option value="prague">00:00 Prague (CE/CEST, FTMO-style)</option>
          <option value="newyork">17:00 New York</option><option value="india">00:00 India</option></select></label>
        <label>Daily loss counted from <select id="jaBase"><option value="initial">the account size</option><option value="day_start">that day's starting balance</option></select></label></div>
      <div class="meta">Static max loss = fixed level below the phase's starting balance. Trailing = follows your highest balance.
        Consistency % = your best single day may be at most this share of the total profit (e.g. 40); leave empty if your firm has no such rule.</div>
      <label class="meta" style="display:block;margin-top:10px">Notes (payout dates, login, anything)<textarea id="jaNotes" rows="3">${esc(a ? a.notes || "" : "")}</textarea></label>
      <div class="frm" style="margin-top:12px"><button class="primary" data-j="saveacc">${a ? "Save changes" : "Create account"}</button>
        <span class="warn" id="jaErr"></span></div>
      ${a ? `<div class="meta">Changing the rules re-checks every past trade with the new rules.</div>` : ""}
    </div>`;
  $("jaReset").value = r.reset || "utc"; $("jaBase").value = r.daily_base || "initial";
  $("modal").hidden = false;
}
function readPhases() {
  return [...document.querySelectorAll("#jaPhases .prow")].map(row => ({ name: row.querySelector(".pn").value, target_pct: row.querySelector(".pt").value,
    daily_loss_pct: row.querySelector(".pd").value, max_loss_pct: row.querySelector(".pm").value, max_loss_type: row.querySelector(".pty").value,
    min_days: row.querySelector(".pmd").value, consistency_pct: row.querySelector(".pc").value }));
}
function readRules() {
  const f = $("jaFunded");
  return { phases: readPhases(), funded: { daily_loss_pct: f.querySelector(".pd").value, max_loss_pct: f.querySelector(".pm").value,
           max_loss_type: f.querySelector(".pty").value, profit_split: f.querySelector(".ps").value, consistency_pct: f.querySelector(".pc").value },
           reset: $("jaReset").value, daily_base: $("jaBase").value };
}

// ---------- Trade form ----------
function tradeForm(t, prefill) {
  const accs = J.accounts.filter(a => !a.archived && a.current && !a.current.result);
  const accId = t ? t.account_id : (J.acc ? J.acc.id : accs[0] && accs[0].id);
  if (!accId) { alert("Create an account first (Home → New account)."); return; }
  const v = Object.assign({ side: "BUY", symbol: "XAUUSD", opened_at: Math.round(Date.now() / 1000) }, prefill || {}, t || {});
  const known = [...new Set([...SETUPS, ...((J.acc && J.acc.trades) || []).map(x => x.setup).filter(Boolean)])];
  const pool = t ? [...J.accounts] : accs;
  if (t && J.acc && J.acc.id === t.account_id && !pool.some(a => a.id === t.account_id)) pool.unshift(J.acc);
  const accOpts = pool.map(a => `<option value="${a.id}" ${a.id === accId ? "selected" : ""}>${esc(a.name)}${a.archived ? " (archived)" : ""}</option>`).join("");
  $("modalBody").innerHTML = `<h2>${t ? "Trade" : v.source === "auedge" ? "Add AuEdge call to journal" : "Add trade"}</h2>
    <div class="jform">
      <div class="frm"><label>Account <select id="jtAcc">${accOpts}</select></label><label>Phase <select id="jtPhase"></select></label>
        <label>Symbol <input id="jtSym" value="${esc(v.symbol)}" style="width:90px"></label></div>
      <div class="frm"><div class="seg" id="jtSide"><button data-side="BUY" class="${v.side === "BUY" ? "on" : ""}">BUY</button><button data-side="SELL" class="${v.side === "SELL" ? "on" : ""}">SELL</button></div>
        <label>Opened <input id="jtOpen" type="datetime-local" value="${toLocalInput(v.opened_at)}"></label>
        <label>Closed <input id="jtClose" type="datetime-local" value="${toLocalInput(v.closed_at)}"></label></div>
      <div class="frm"><label>Lots <input id="jtLots" type="number" step="0.01" value="${v.lots ?? ""}"></label>
        <label>Entry <input id="jtEntry" type="number" step="0.01" value="${v.entry ?? ""}"></label>
        <label>Stop <input id="jtStop" type="number" step="0.01" value="${v.stop ?? ""}"></label>
        <label>Target <input id="jtTarget" type="number" step="0.01" value="${v.target ?? ""}"></label>
        <label>Exit <input id="jtExit" type="number" step="0.01" value="${v.exit ?? ""}"></label></div>
      <div class="jrisk meta" id="jtRisk"></div>
      <div class="frm"><label title="Your broker's real profit/loss. Leave empty to work it out from entry, exit and lots.">P&amp;L $ <input id="jtPnl" type="number" step="0.01" value="${v.pnl ?? ""}" placeholder="auto"></label>
        <label>Commission $ <input id="jtCom" type="number" step="0.01" value="${v.commission || ""}"></label>
        <label>Setup <input id="jtSetup" list="jtSetups" value="${esc(v.setup || "")}" style="width:170px"></label>
        <datalist id="jtSetups">${known.map(x => `<option value="${esc(x)}">`).join("")}</datalist></div>
      <div class="frm"><span>Followed my plan?</span><div class="seg" id="jtPlan"><button data-plan="1" class="${v.followed_plan === 1 ? "on" : ""}">Yes</button>
          <button data-plan="0" class="${v.followed_plan === 0 ? "on" : ""}">No</button></div>
        <span>Rating</span><div class="jstars" id="jtRate">${[1, 2, 3, 4, 5].map(n => `<button data-rate="${n}" class="${(v.rating || 0) >= n ? "on" : ""}" aria-label="${n} stars">★</button>`).join("")}</div></div>
      <div class="frm"><span>Mood</span><div class="jmoods" id="jtMood">${EMOTIONS.map(e => `<button data-mood="${e}" class="${v.emotion === e ? "on" : ""}">${e}</button>`).join("")}</div></div>
      <label class="meta" style="display:block">Mistakes / lessons<textarea id="jtMist" rows="2">${esc(v.mistakes || "")}</textarea></label>
      <label class="meta" style="display:block;margin-top:6px">Notes<textarea id="jtNotes" rows="3">${esc(v.notes || "")}</textarea></label>
      <div class="frm" style="margin-top:6px"><label>Screenshot <input id="jtImg" type="file" accept="image/png,image/jpeg,image/webp"></label>
        <span class="meta">or paste an image (Ctrl+V) while this form is open</span></div>
      <div id="jtImgPrev">${v.image ? `<img src="/api/journal/file/${esc(v.image)}" alt="Trade screenshot" class="jimg"><button class="linkbtn" data-j="rmimg">Remove screenshot</button>` : ""}</div>
      ${v.auedge ? `<div class="meta">From AuEdge: ${esc(v.auedge.action || "")} · confidence ${v.auedge.confidence ?? "—"}% · ${jDate(v.auedge.t)}</div>` : ""}
      <div class="frm" style="margin-top:12px"><button class="primary" data-j="savetrade">${t ? "Save" : "Add to journal"}</button>
        ${t ? `<button data-j="deltrade" class="dnbtn">Delete trade</button>` : ""}<span class="warn" id="jtErr"></span></div>
    </div>`;
  J.form = { t, v, image: null, side: v.side, plan: v.followed_plan ?? null, rate: v.rating || 0, mood: v.emotion || null };
  const fillPhases = () => { const a = (J.acc && J.acc.id === +$("jtAcc").value) ? J.acc : J.accounts.find(x => x.id === +$("jtAcc").value) || J.acc;
    const phs = (J.acc && J.acc.id === a.id ? J.acc.phases : a.phases);
    $("jtPhase").innerHTML = phs.map(p => `<option value="${p.id}" ${(t ? t.phase_id === p.id : !p.result) ? "selected" : ""}>${p.is_funded ? "Funded" : esc(p.name)}${p.result ? ` (${p.result})` : ""}</option>`).join("");
    riskHint(); };
  $("jtAcc").onchange = fillPhases; fillPhases();
  for (const id of ["jtLots", "jtEntry", "jtStop", "jtExit", "jtPnl"]) $(id).addEventListener("input", riskHint);
  $("jtImg").onchange = e => readImg(e.target.files[0]);
  $("modal").hidden = false;
}
function riskHint() {
  const a = J.accounts.find(x => x.id === +$("jtAcc").value); if (!a || !$("jtRisk")) return;
  const c = a.current.check, lots = +$("jtLots").value, e = +$("jtEntry").value, st = +$("jtStop").value, ex = +$("jtExit").value;
  const parts = [];
  if (lots && e && st) { const risk = Math.abs(e - st) * lots * 100;
    parts.push(`Risk if the stop is hit: <b>$${risk.toFixed(0)}</b> (${(100 * risk / a.size).toFixed(2)}% of the account)`);
    if (c.daily_room != null) parts.push(risk > c.daily_room ? `<span class="dn">more than today's loss room ($${Math.round(c.daily_room)})!</span>` : `today's loss room left: $${Math.round(c.daily_room)}`); }
  if (e && st) { const perLot = Math.abs(e - st) * 100;
    parts.push(`Lots for 0.5% risk: <b>${(a.size * 0.005 / perLot).toFixed(2)}</b> · for 1%: <b>${(a.size * 0.01 / perLot).toFixed(2)}</b>`); }
  if (lots && e && ex && $("jtPnl").value === "") parts.push(`P&L from prices: <b>${jUsd(Math.round((ex - e) * (J.form.side === "BUY" ? 1 : -1) * lots * 100 * 100) / 100)}</b> (type your broker's number if different)`);
  $("jtRisk").innerHTML = parts.join(" · ");
}
function readImg(file) {
  if (!file) return;
  if (file.size > 6 * 1024 * 1024) { alert("Screenshot must be under 6 MB."); return; }
  const r = new FileReader();
  r.onload = () => { J.form.image = r.result; $("jtImgPrev").innerHTML = `<img src="${r.result}" alt="Trade screenshot" class="jimg">`; };
  r.readAsDataURL(file);
}
document.addEventListener("paste", e => {
  if ($("modal").hidden || !$("jtImgPrev")) return;
  const item = [...(e.clipboardData || {}).items || []].find(i => i.type.startsWith("image/"));
  if (item) { e.preventDefault(); readImg(item.getAsFile()); }
});
function tradeBody() {
  const n = id => $(id).value === "" ? null : +$(id).value;
  return { account_id: +$("jtAcc").value, phase_id: +$("jtPhase").value, symbol: $("jtSym").value, side: J.form.side,
    opened_at: fromLocalInput($("jtOpen").value), closed_at: fromLocalInput($("jtClose").value), lots: n("jtLots"), entry: n("jtEntry"),
    stop: n("jtStop"), target: n("jtTarget"), exit: n("jtExit"), pnl: n("jtPnl"), commission: n("jtCom"), setup: $("jtSetup").value,
    followed_plan: J.form.plan, rating: J.form.rate || null, emotion: J.form.mood, mistakes: $("jtMist").value, notes: $("jtNotes").value,
    source: J.form.v.source, auedge: J.form.v.auedge, image_data: J.form.image };
}

// ---------- AuEdge call → journal ----------
function addCall() {
  const d = agentState.data; if (!d) return;
  const p = d.chief.plan; if (p.kind !== "now") return;
  const go = () => tradeForm(null, { side: p.side, entry: Math.round((p.entry_lo + p.entry_hi) / 2 * 100) / 100, stop: p.stop, target: p.t1,
    setup: "AuEdge NOW call", source: "auedge", opened_at: Math.round(Date.now() / 1000),
    auedge: { action: p.action, confidence: d.chief.confidence, t: Math.round(Date.parse(d.generated_at) / 1000), be_at: p.be_at } });
  J.accounts.length ? go() : jApi("/api/journal/accounts").then(r => { J.accounts = r.accounts; go(); });
}

// ---------- events ----------
async function jClick(e) {
  const acc = e.target.closest("[data-acc]"), ph = e.target.closest("[data-ph]"), tr = e.target.closest("[data-trade]");
  const j = e.target.closest("[data-j]"), go = e.target.closest("[data-view-go]");
  const sub = e.target.closest("[data-sub]"), jcal = e.target.closest("[data-jcal]"), jday = e.target.closest("[data-jday]");
  if (sub) { J.sub = sub.dataset.sub; lsSet("jSub", J.sub); J.calDay = null; return renderAccount(); }
  if (jcal) { J.calMonth = new Date(J.calMonth.getFullYear(), J.calMonth.getMonth() + +jcal.dataset.jcal, 1); J.calDay = null;
              return J.page === "records" ? renderRecords() : renderAccount(); }
  if (jday) { J.calDay = J.calDay === jday.dataset.jday ? null : jday.dataset.jday; return J.page === "records" ? renderRecords() : renderAccount(); }
  if (go) return setView(go.dataset.viewGo);
  if (e.target.closest("[data-demo-journal]") && e.type === "keydown") return openDemoJournal();
  if (e.target.closest("[data-demo-open]") && e.type === "keydown") return openDemoTab();
  if (e.target.closest("[data-jn-call]")) return addCall();
  if (j) {
    const k = j.dataset.j, a = J.acc;
    if (k === "new") return accountForm(null);
    if (k === "archived") { J.archived = !J.archived; return loadHome(); }
    if (k === "back") { J.acc = null; J.phaseSel = null; J.page = "home"; return loadHome(); }
    if (k === "records") return openRecords();
    if (k === "csv") return downloadCsv();
    if (k === "rlist" || k === "rcal") { J.rec.cal = k === "rcal"; J.calDay = null; return renderRecords(); }
    if (k === "clearf") { J.rec.f = {}; return renderRecords(); }
    if (k === "trade") { if (!J.accounts.length) J.accounts = (await jApi("/api/journal/accounts")).accounts; return tradeForm(null); }
    if (k === "edit") return accountForm(a);
    if (k === "archive") { await jApi(`/api/journal/accounts/${a.id}`, "PUT", { name: a.name, firm: a.firm, notes: a.notes, archived: !a.archived }); return openAccount(a.id); }
    if (k === "pass" || k === "fail") {
      const p = J.phaseSel, what = k === "pass" ? "passed" : "failed";
      const note = prompt(`Mark ${p.is_funded ? "the funded account" : p.name} as ${what}? Optional note (e.g. "firm confirmed on 3 Nov"):`, "");
      if (note === null) return;
      let nb = null;
      if (k === "pass") { const v = prompt(`Starting balance of the next phase ($):`, String(a.size)); if (v === null) return; nb = +v || a.size; }
      const r = await jApi(`/api/journal/accounts/${a.id}/advance`, "POST", { result: what, note, next_balance: nb });
      if (!r.ok) return alert(r.error);
      J.phaseSel = null; return openAccount(a.id);
    }
    if (k === "reopen") { if (!confirm("Undo the last passed / failed mark?")) return; const r = await jApi(`/api/journal/accounts/${a.id}/reopen`, "POST");
      if (!r.ok) return alert(r.error); J.phaseSel = null; return openAccount(a.id); }
  }
  if (ph && J.acc) { J.phaseSel = J.acc.phases.find(p => p.id === +ph.dataset.ph); return renderAccount(); }
  if (tr && J.page === "records") { const t = J.rec.trades.find(x => x.id === +tr.dataset.trade); J.acc = await jApi(`/api/journal/accounts/${t.account_id}`);
    J.recReturn = true; return tradeForm(J.acc.trades.find(x => x.id === t.id)); }
  if (tr && J.acc) { if (!J.accounts.length) J.accounts = (await jApi("/api/journal/accounts")).accounts; return tradeForm(J.acc.trades.find(t => t.id === +tr.dataset.trade)); }
  if (acc && !j) { J.phaseSel = null; J.page = "account"; J.calMonth = null; J.calDay = null; return openAccount(+acc.dataset.acc); }
}
$("homeView").addEventListener("click", jClick);
$("homeView").addEventListener("change", e => { const f = e.target.closest("[data-rf]"); if (!f) return; J.rec.f[f.dataset.rf] = f.value; J.calDay = null; renderRecords(); });
$("homeView").addEventListener("keydown", e => { if ((e.key === "Enter" || e.key === " ") && e.target.matches("[data-acc], [data-j], [data-trade], [data-demo-open], [data-demo-journal]")) { e.preventDefault(); jClick(e); } });
document.addEventListener("click", e => { if (e.target.closest("#tab-plan [data-jn-call]")) addCall(); });
$("modalBody").addEventListener("click", async e => {
  const pre = e.target.closest("[data-preset]"), rm = e.target.closest("[data-prm]"), j = e.target.closest("[data-j]");
  const side = e.target.closest("[data-side]"), plan = e.target.closest("[data-plan]"), rate = e.target.closest("[data-rate]"), mood = e.target.closest("[data-mood]");
  if (pre) { const P = PRESETS[pre.dataset.preset]; $("jaPhases").innerHTML = P.phases.map(phaseRow).join("");
    const f = $("jaFunded"); f.querySelector(".pd").value = P.funded.daily_loss_pct; f.querySelector(".pm").value = P.funded.max_loss_pct;
    f.querySelector(".pty").value = P.funded.max_loss_type; f.querySelector(".ps").value = P.funded.profit_split; return; }
  if (rm) { const ps = readPhases(); if (ps.length <= 1) return; ps.splice(+rm.dataset.prm, 1); $("jaPhases").innerHTML = ps.map(phaseRow).join(""); return; }
  if (side) { J.form.side = side.dataset.side; for (const b of document.querySelectorAll("#jtSide button")) b.classList.toggle("on", b === side); return riskHint(); }
  if (plan) { J.form.plan = J.form.plan === +plan.dataset.plan ? null : +plan.dataset.plan; for (const b of document.querySelectorAll("#jtPlan button")) b.classList.toggle("on", +b.dataset.plan === J.form.plan); return; }
  if (rate) { J.form.rate = +rate.dataset.rate; for (const b of document.querySelectorAll("#jtRate button")) b.classList.toggle("on", +b.dataset.rate <= J.form.rate); return; }
  if (mood) { J.form.mood = J.form.mood === mood.dataset.mood ? null : mood.dataset.mood; for (const b of document.querySelectorAll("#jtMood button")) b.classList.toggle("on", b.dataset.mood === J.form.mood); return; }
  if (!j) return;
  const k = j.dataset.j;
  if (k === "addphase") { const ps = readPhases(); if (ps.length >= 5) return; const l = ps[ps.length - 1] || {};
    ps.push({ name: `Phase ${ps.length + 1}`, target_pct: "", daily_loss_pct: l.daily_loss_pct, max_loss_pct: l.max_loss_pct, max_loss_type: l.max_loss_type,
              min_days: l.min_days, consistency_pct: l.consistency_pct });
    $("jaPhases").innerHTML = ps.map(phaseRow).join(""); return; }
  if (k === "saveacc") {
    const body = { name: $("jaName").value.trim(), firm: $("jaFirm").value.trim(), size: +$("jaSize").value, notes: $("jaNotes").value, rules: readRules() };
    const r = J.acc && $("jaSize").disabled ? await jApi(`/api/journal/accounts/${J.acc.id}`, "PUT", body) : await jApi("/api/journal/accounts", "POST", body);
    if (r.ok === false) { $("jaErr").textContent = r.error; return; }
    $("modal").hidden = true;
    if (r.id) { await loadHome(); return openAccount(r.id); }
    return openAccount(J.acc.id);
  }
  if (k === "rmimg") { J.form.image = "remove"; $("jtImgPrev").innerHTML = `<span class="meta">Screenshot will be removed when you save.</span>`; return; }
  if (k === "savetrade") {
    const body = tradeBody();
    if (!body.opened_at) { $("jtErr").textContent = "Set the open time."; return; }
    const r = J.form.t ? await jApi(`/api/journal/trades/${J.form.t.id}`, "PUT", body) : await jApi("/api/journal/trades", "POST", body);
    if (!r.ok) { $("jtErr").textContent = r.error; return; }
    $("modal").hidden = true;
    J.accounts = (await jApi("/api/journal/accounts")).accounts;
    if (J.recReturn) { J.recReturn = false; return openRecords(); }
    if (document.body.classList.contains("view-home")) { if (J.acc) openAccount(body.account_id, body.phase_id); else renderHome(); }
    else { J.acc = null; setView("home"); openAccount(body.account_id, body.phase_id); }
    return;
  }
  if (k === "deltrade") { if (!confirm("Delete this trade from the journal? This cannot be undone.")) return;
    await jApi(`/api/journal/trades/${J.form.t.id}`, "DELETE"); $("modal").hidden = true; J.accounts = (await jApi("/api/journal/accounts")).accounts;
    if (J.recReturn) { J.recReturn = false; return openRecords(); } return openAccount(J.acc.id); }
});

window.jOnAnalysis = () => { if ($("todayStrip")) $("todayStrip").innerHTML = todayHtml(); };
setView(lsGet("view", "home") === "trade" ? "trade" : "home");
setInterval(() => { if (document.body.classList.contains("view-home") && J.page === "home" && !J.acc && $("modal").hidden) loadHome(); }, 60000);

// closing the trade form without saving: drop the All-records context so the next click opens the right trade
$("modalClose").addEventListener("click", () => { if (J.recReturn) { J.recReturn = false; J.acc = null; } });
$("modal").addEventListener("click", e => { if (e.target.id === "modal" && J.recReturn) { J.recReturn = false; J.acc = null; } });
document.addEventListener("keydown", e => { if (e.key === "Escape" && J.recReturn) { J.recReturn = false; J.acc = null; } });
