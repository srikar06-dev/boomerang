"use strict";
// Reviewer queue: list returns, open the evidence for one, approve or keep on hold.

const $ = (id) => document.getElementById(id);
let current = null;

async function load() {
  $("error").textContent = "";
  try {
    const decision = $("filter").value;
    const data = await api("/returns" + (decision ? `?decision=${encodeURIComponent(decision)}` : ""), { staff: true });
    const rows = data.returns.map((r) => {
      const tr = el("tr", { class: "pick", tabindex: "0" },
        el("td", {}, when(r.created_at)),
        el("td", {}, `${r.order_id} (${r.sku || "?"})`),
        el("td", {}, badge(r.decision)),
        el("td", {}, Number(r.risk_score ?? 0).toFixed(2)),
        el("td", {}, (r.reasons || []).join(", ")),
        el("td", {}, r.review ? `${r.review.action} by ${r.review.reviewer}` : ""));
      const open = () => openDetail(r.return_id);
      tr.addEventListener("click", open);
      tr.addEventListener("keydown", (e) => { if (e.key === "Enter") open(); });
      return tr;
    });
    $("rows").replaceChildren(...rows);
    $("empty").textContent = rows.length ? "" : "Nothing here.";
  } catch (e) {
    $("error").textContent = e.message;
  }
}

function photos(urls) {
  if (!urls.length) return [el("p", { class: "muted" }, "No photos on record")];
  return urls.map((u) => el("img", { class: "shot", src: u, alt: "Evidence photo", referrerpolicy: "no-referrer" }));
}

async function openDetail(id) {
  $("detail-error").textContent = "";
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
      ["Review", r.review ? `${r.review.action} by ${r.review.reviewer}: ${r.review.note || ""}` : "not reviewed"],
    ];
    $("facts").replaceChildren(...facts.flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)]));
    show($("detail"), true);
    $("detail").scrollIntoView({ behavior: "smooth" });
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
    await openDetail(current);
    await load();
  } catch (e) {
    $("detail-error").textContent = e.message;
  }
}

$("approve").addEventListener("click", () => decide("approve"));
$("hold").addEventListener("click", () => decide("hold"));
$("filter").addEventListener("change", load);
setupStaffBar(load);
