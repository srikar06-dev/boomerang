"use strict";
// Dashboard: headline numbers, decisions by type, and the test-set scorecard. Refreshes every 5 s.

const $ = (id) => document.getElementById(id);
let timer = null;

function tile(num, cap) { return el("div", { class: "tile" }, el("div", { class: "num" }, num), el("div", { class: "cap" }, cap)); }

async function load() {
  try {
    const s = await api("/stats", { staff: true });
    $("error").textContent = "";
    $("tiles").replaceChildren(
      tile(s.total, "Returns checked"),
      tile(money(s.money_held_usd), "Refunds held for a person"),
      tile(money(s.instant_refunds_usd), "Instant refunds issued"),
      tile(money(s.shipping_avoided_usd), "Return shipping avoided"),
      tile(money(s.net_recovery_usd), "Estimated resale recovery"),
      tile(s.awaiting_review, "Waiting for review"));

    renderImpact(s.impact);
    renderEstimate(s.us_estimate);

    const max = Math.max(1, ...DECISIONS.map((d) => s.by_decision[d] || 0));
    $("bars").replaceChildren(...DECISIONS.map((d) => {
      const n = s.by_decision[d] || 0;
      const fill = el("div", { class: `fill ${d}` });
      fill.style.width = `${(100 * n) / max}%`;
      return el("div", { class: "bar" }, el("span", { class: "name" }, d), el("div", { class: "track" }, fill), el("span", {}, n));
    }));

    const t = s.test_set;
    const rows = [
      ["Frauds caught (yellow, red or review)", "at least 8 of 10", `${t.fraud_caught} of ${t.fraud_total}`],
      ["Honest returns flagged (red or review)", "at most 1 of 10", `${t.honest_flagged} of ${t.honest_total}`],
      ["Instant refunds given on fraud", "0", String(t.fraud_instant_refunds)],
    ];
    $("metrics").replaceChildren(...rows.map((r) => el("tr", {}, ...r.map((c) => el("td", {}, c)))));
    if (!timer) timer = setInterval(load, 5000);
  } catch (e) {
    $("error").textContent = e.message;
    clearInterval(timer); timer = null;
  }
}

function kg(n) { return `${Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 1 })} kg`; }

function renderImpact(m) {
  if (!m) return;
  $("impact").replaceChildren(
    tile(kg(m.co2_avoided_kg), "CO2 avoided (estimate)"),
    tile(m.trips_avoided, "Parcel trips avoided"),
    tile(`${m.wrong_picks_stopped} / ${money(m.wrong_pick_cost_avoided_usd)}`, "Wrong picks stopped before shipping"),
    tile(kg(m.kept_in_use_kg), `Kept in use (${m.kept_in_use_items} items resold)`),
    tile(money(m.refunds_stopped_usd), "Refunds stopped (RED)"),
    tile(m.unsafe_items_kept_off_shelves, "Opened consumables kept off shelves"));
  const n = m.returns_counted;
  $("scale").textContent = n
    ? `At this rate, 100,000 returns a year would avoid about ${((m.co2_avoided_kg / n) * 100).toFixed(1)} t CO2 ` +
      `and ${Math.round((m.ship_backs_avoided / n) * 100000).toLocaleString()} trips back to the warehouse.`
    : "No returns checked yet.";
  const a = m.assumptions;
  $("assumptions").replaceChildren(...[
    `CO2: ${a.parcel_trip_kg_co2} kg CO2e per parcel trip avoided (Oliver Wyman 2023: 1 kg parcel, home delivery).`,
    "Trips avoided: returns resold locally, donated or disposed of skip the trip back; a stopped wrong pick skips the return and the reshipment.",
    `Return label ${money(a.return_label_usd)} (US average $8-12 per item); wrong pick ${money(a.wrong_pick_cost_usd)} each (Intermec / Honeywell survey).`,
    "Kept in use: items restocked, sold open-box, refurbished or resold locally instead of liquidated or landfilled.",
  ].map((t) => el("li", {}, t)));
}

const M = (n) => (Math.abs(n) >= 1000 ? `$${(n / 1000).toFixed(2)}B` : `$${Number(n).toFixed(1)}M`);
const N = (n, d = 0) => Number(n).toLocaleString(undefined, { maximumFractionDigits: d });
const PCT = new Set(["return_rate", "adoption", "fraud_share", "fraud_catch", "mispick_rate", "mispick_catch",
                     "low_value_share", "green_share"]);

function row(label, values, bold) {
  const cells = values.map((v) => el("td", {}, v));
  const head = el("td", {}, label);
  if (bold) [head, ...cells].forEach((c) => (c.style.fontWeight = "600"));
  return el("tr", {}, head, ...cells);
}

function renderEstimate(e) {
  if (!e) return;
  const keys = Object.keys(e.sources);
  const ref = (k) => (k ? `[${keys.indexOf(k) + 1}]` : "assumption");
  const sc = ["conservative", "base", "optimistic"].map((k) => e.scenarios[k]);
  const col = (f) => sc.map(f);
  $("us-results").replaceChildren(
    row("Returns checked", col((s) => `${N(s.returns_m, 1)}M`)),
    row("Fraud refunds stopped", col((s) => M(s.fraud_stopped_musd))),
    row("Wrong picks stopped (cost)", col((s) => M(s.wrong_pick_musd))),
    row("Return shipping avoided", col((s) => M(s.shipping_musd))),
    row("Grading labor saved", col((s) => M(s.grading_musd))),
    row("Running cost (model + staff time)", col((s) => `-${M(s.running_musd)}`)),
    row("Net savings", col((s) => M(s.net_musd)), true),
    row("Net saving per return", col((s) => `$${s.net_per_return_usd.toFixed(2)}`)),
    row("Parcel trips avoided", col((s) => `${N(s.trips_avoided_m, 1)}M`)),
    row("CO2 avoided", col((s) => `${N(s.co2_t)} t`), true));
  $("us-per100k").replaceChildren(
    row("Fraud refunds stopped", col((s) => money(s.per_100k.fraud_usd))),
    row("Wrong-pick cost avoided", col((s) => money(s.per_100k.wrong_pick_usd))),
    row("Return shipping avoided", col((s) => money(s.per_100k.shipping_usd))),
    row("Grading labor saved", col((s) => money(s.per_100k.grading_usd))),
    row("Running cost", col((s) => `-${money(s.per_100k.running_usd)}`)),
    row("Net savings", col((s) => money(s.per_100k.net_usd)), true),
    row("CO2 avoided", col((s) => `${N(s.per_100k.co2_t, 1)} t`)));
  const fmt = (k, v) => (PCT.has(k) ? `${N(v * 100, 1)}%` : N(v, v < 1 ? 5 : 3));
  $("us-inputs").replaceChildren(...e.inputs.map((i) => el("tr", {},
    el("td", {}, i.label), ...i.values.map((v) => el("td", {}, fmt(i.key, v))),
    el("td", {}, i.measured ? "measured (our test set)" : ref(i.source)))));
  $("us-sources").replaceChildren(...keys.map((k) => el("li", {},
    el("a", { href: e.sources[k].url, target: "_blank", rel: "noopener" }, e.sources[k].title))));
}

setupStaffBar(load);
