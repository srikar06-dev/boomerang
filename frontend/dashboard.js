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

setupStaffBar(load);
