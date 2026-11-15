"use strict";
// Packages: every order in one table (ship-out fingerprint + latest return), searchable, CSV export.

const $ = (id) => document.getElementById(id);
let data = [];
let timer = null;

function tile(num, cap, kind = "") {
  return el("div", { class: `tile ${kind}` }, el("div", { class: "num" }, num), el("div", { class: "cap" }, cap));
}
const day = (iso) => {
  const d = new Date(iso);
  return isNaN(d) ? "" : d.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
};
const UNIT = { device: "serial on device", box: "box label only", none: "no serial" };

function shipCell(p) {
  const s = p.shipout;
  if (!s) return el("span", { class: "muted" }, "not shipped");
  const facts = [s.weight_g != null ? `${s.weight_g} g` : "no weight", s.serial || "no serial", `${s.photos} photos`];
  const pick = s.pick_verified === true ? el("span", { class: "pill-good" }, "pick ✓")
    : s.pick_verified === false ? el("span", { class: "pill-bad" }, "shipped anyway") : "";
  return el("div", {}, el("div", {}, day(p.shipped_at)), el("div", { class: "muted" }, facts.join(" · ")), pick);
}

function returnCell(p) {
  const r = p.return;
  if (!r) return el("span", { class: "muted" }, "—");
  const extra = [r.disposition, r.weight_g != null ? `${r.weight_g} g` : null].filter(Boolean).join(" · ");
  return el("div", {}, badge(r.decision), " ", el("span", { class: "muted" }, day(r.created_at)),
            el("div", { class: "muted" }, extra), el("div", { class: "muted" }, (r.reasons || []).join(", ")));
}

function reviewCell(p) {
  const r = p.return;
  if (!r) return el("span", { class: "muted" }, "—");
  if (r.review) return el("span", {}, `${r.review} · ${r.reviewer || ""}`);
  return p.held ? el("span", { class: "pill-bad" }, "waiting") : el("span", { class: "muted" }, "not needed");
}

function render() {
  const rows = data.map((p) => {
    const tr = el("tr", p.return ? { class: "pick", tabindex: "0", title: "Open evidence in Review" } : {},
      el("td", { "data-label": "Order" }, el("div", {}, el("div", {}, p.order_id), el("div", { class: "muted" }, p.customer_id || ""))),
      el("td", { "data-label": "Product" }, el("div", {}, el("div", {}, p.product || "?"),
        el("div", { class: "muted" }, [p.price_usd != null ? money(p.price_usd) : null, UNIT[p.unit_id],
          p.sealed_consumable ? "sealed" : null].filter(Boolean).join(" · ")))),
      el("td", { "data-label": "Ship-out" }, shipCell(p)),
      el("td", { "data-label": "Return" }, returnCell(p)),
      el("td", { "data-label": "Review" }, reviewCell(p)));
    if (p.return) {
      const open = () => { window.location.href = `review.html#${encodeURIComponent(p.return.return_id)}`; };
      tr.addEventListener("click", open);
      tr.addEventListener("keydown", (e) => { if (e.key === "Enter") open(); });
    }
    return tr;
  });
  $("rows").replaceChildren(...rows);
  $("empty").textContent = rows.length ? "" : "No packages match.";
}

async function load() {
  try {
    const params = new URLSearchParams({ q: $("q").value.trim(), status: $("status").value });
    const out = await api(`/packages?${params}`, { staff: true });
    data = out.packages;
    const s = out.summary;
    $("summary").replaceChildren(
      tile(out.total, "Packages shown", "info"),
      tile(s.shipped, "Shipped, not returned", "eco"),
      tile(s.returned, "Returned", "money"),
      tile(s.held, "Held for a person", "held"),
      tile(s.not_shipped, "Not shipped yet", ""),
      tile(data.filter((p) => p.shipout && p.shipout.pick_verified === false).length, "Shipped despite pick warning", "risk"));
    $("updated").textContent = `Live · updated ${new Date().toLocaleTimeString()}`;
    $("error").textContent = "";
    render();
    if (!timer) timer = setInterval(load, 10000);
  } catch (e) {
    $("error").textContent = e.message;
    keyProblem(e.message);
    clearInterval(timer); timer = null;
  }
}

function csvCell(v) {
  const s = v == null ? "" : String(v);
  // Quote everything; a leading = + - @ is prefixed so spreadsheets never run it as a formula.
  return `"${(/^[=+\-@]/.test(s) ? `'${s}` : s).replace(/"/g, '""')}"`;
}

function downloadCsv() {
  const head = ["order_id", "customer_id", "product", "sku", "price_usd", "serial_type", "sealed", "shipped_at",
                "shipout_weight_g", "shipout_serial", "shipout_photos", "pick_check", "return_at", "decision",
                "disposition", "return_weight_g", "reasons", "review", "reviewer"];
  const lines = data.map((p) => {
    const s = p.shipout || {}, r = p.return || {};
    return [p.order_id, p.customer_id, p.product, p.sku, p.price_usd, p.unit_id, p.sealed_consumable, p.shipped_at,
            s.weight_g, s.serial, s.photos,
            s.pick_verified === true ? "ok" : s.pick_verified === false ? "shipped anyway" : "",
            r.created_at, r.decision, r.disposition, r.weight_g, (r.reasons || []).join("; "), r.review, r.reviewer]
      .map(csvCell).join(",");
  });
  const blob = new Blob([[head.join(","), ...lines].join("\r\n")], { type: "text/csv" });
  const a = el("a", { href: URL.createObjectURL(blob), download: `boomerang-packages-${new Date().toISOString().slice(0, 10)}.csv` });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

let typing = null;
$("q").addEventListener("input", () => { clearTimeout(typing); typing = setTimeout(load, 300); });
$("status").addEventListener("change", load);
$("csv").addEventListener("click", downloadCsv);
// New item: POST /orders creates a product + one order, so staff can ship it out right away.
async function createItem() {
  const err = document.getElementById("ni-error"), done = document.getElementById("ni-done");
  const btn = document.getElementById("ni-create");
  err.textContent = ""; show(done, false);
  const name = document.getElementById("ni-name").value.trim();
  const price = parseFloat(document.getElementById("ni-price").value);
  const weightText = document.getElementById("ni-weight").value.trim();
  if (!name) { err.textContent = "Enter an item name."; return; }
  if (!(price >= 0)) { err.textContent = "Enter a price."; return; }
  const body = { name, price_usd: price, has_serial: document.getElementById("ni-serial").value === "yes" };
  if (weightText) body.weight_g = parseFloat(weightText);
  btn.disabled = true;
  try {
    const out = await api("/orders", { method: "POST", body, staff: true });
    done.replaceChildren("Created ", el("strong", {}, out.order_id), ` for ${out.name}. `,
      el("a", { href: "capture.html" }, "Ship it out on Capture"));
    show(done, true);
    document.getElementById("ni-name").value = "";
    document.getElementById("ni-price").value = "";
    document.getElementById("ni-weight").value = "";
    load();
  } catch (e) {
    err.textContent = e.message; keyProblem(e.message);
  } finally {
    btn.disabled = false;
  }
}
document.getElementById("ni-create").addEventListener("click", createItem);

setupStaffBar(load);
