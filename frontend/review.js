"use strict";
// Reviewer queue: list returns, open the evidence for one, approve, reject or keep on hold.
// The reviewer name is typed for each decision and never carried over to the next one.

const $ = (id) => document.getElementById(id);
let current = null;

async function load() {
  $("error").textContent = "";
  try {
    const decision = $("filter").value;
    const data = await api("/returns" + (decision ? `?decision=${encodeURIComponent(decision)}` : ""), { staff: true });
    const rows = data.returns.map((r) => {
      const tr = el("tr", { class: "pick", tabindex: "0" },
        el("td", { class: "muted" }, shortWhen(r.created_at)),
        el("td", {}, el("div", {}, r.order_id), el("div", { class: "muted" }, (r.reasons || []).join(", "))),
        el("td", {}, badge(r.decision)),
        el("td", { class: "num" }, Number(r.risk_score ?? 0).toFixed(2)),
        el("td", {}, r.review ? `${r.review.action} · ${r.review.reviewer}` : el("span", { class: "muted" }, "—")));
      tr.dataset.id = r.return_id;
      if (r.return_id === current) tr.classList.add("active");
      const open = () => openDetail(r.return_id);
      tr.addEventListener("click", open);
      tr.addEventListener("keydown", (e) => { if (e.key === "Enter") open(); });
      return tr;
    });
    $("rows").replaceChildren(...rows);
    $("count").textContent = rows.length ? `${rows.length} shown` : "";
    $("empty").textContent = rows.length ? "" : "Nothing here.";
  } catch (e) {
    $("error").textContent = e.message;
    keyProblem(e.message);
  }
}

function shortWhen(iso) {           // "10:01 PM" today, "Nov 13, 10:01 PM" otherwise
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const t = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return d.toDateString() === new Date().toDateString() ? t
    : `${d.toLocaleDateString([], { month: "short", day: "numeric" })}, ${t}`;
}

function photos(urls) {
  if (!urls.length) return [el("p", { class: "muted" }, "No photos on record")];
  return urls.map((u) => el("img", { class: "shot", src: u, alt: "Evidence photo", referrerpolicy: "no-referrer" }));
}

function clearForm() { $("reviewer").value = ""; $("note").value = ""; }

async function openDetail(id, keepForm = false) {
  $("detail-error").textContent = "";
  if (!keepForm && id !== current) clearForm();
  document.querySelectorAll("tr.pick").forEach((tr) => tr.classList.toggle("active", tr.dataset.id === id));
  try {
    const e = await api(`/evidence/${encodeURIComponent(id)}`, { staff: true });
    current = id;
    const r = e.return, c = r.checks || {}, fp = e.shipout_fingerprint || {};
    $("detail-title").replaceChildren(`Order ${r.order_id} `, badge(r.decision));
    $("ship-photos").replaceChildren(...photos(e.photos.shipout));
    $("return-photos").replaceChildren(...photos(e.photos.return));
    const facts = [
      ["Reasons", (r.reasons || []).join(", ") || "none"],
      ["Risk score", Number(r.risk_score ?? 0).toFixed(2)],
      ["Ship-out weight", fp.weight_g != null ? `${fp.weight_g} g` : "not recorded"],
      ["Return weight", r.return_weight_g != null ? `${r.return_weight_g} g (${c.weight_delta_pct ?? "?"}%)` : "not read"],
      ["Ship-out serial", fp.serial || "none"],
      ["Serial read on return", (r.vision && r.vision.serial_read) || "not read"],
      ["Code visible", c.code_visible ? "yes" : "no"],
      ["Photo seen before", c.phash_reused ? "yes" : "no"],
      ["Same unit (model)", c.same_unit == null ? "no answer" : c.same_unit ? "yes" : "no"],
      ["New damage", (c.new_damage || []).join(", ") || "none"],
      ["Model notes", (r.vision && r.vision.notes) || ""],
      ["Model used", r.model_used],
      ["Photo SHA-256", (r.sha256 || []).map((h) => h.slice(0, 16) + "...").join("  ")],
      ["Review", r.review ? `${r.review.action} by ${r.review.reviewer}${r.review.note ? `: ${r.review.note}` : ""}` : "not reviewed"],
    ];
    $("facts").replaceChildren(...facts.flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)]));
    show($("detail"), true);
    show($("detail-empty"), false);
    if (window.matchMedia("(max-width: 899px)").matches) $("detail-card").scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    $("error").textContent = err.message;
  }
}

async function decide(action) {
  $("detail-error").textContent = "";
  const reviewer = $("reviewer").value.trim();
  if (!reviewer) { $("detail-error").textContent = "Enter your name first."; return; }
  try {
    await api(`/review/${encodeURIComponent(current)}`, { method: "POST", staff: true,
      body: { action, reviewer, note: $("note").value.trim() } });
    clearForm();                 // the next decision needs its own name
    await openDetail(current, true);
    await load();
  } catch (e) {
    $("detail-error").textContent = e.message;
  }
}

$("approve").addEventListener("click", () => decide("approve"));
$("hold").addEventListener("click", () => decide("hold"));
$("reject").addEventListener("click", () => decide("reject"));
$("filter").addEventListener("change", load);
// Opened from the Packages page as review.html#<return_id>: show that return straight away.
setupStaffBar(async () => {
  await load();
  const id = decodeURIComponent(window.location.hash.slice(1));
  if (id && id !== current) {
    $("filter").value = "";
    await load();
    openDetail(id);
  }
});
