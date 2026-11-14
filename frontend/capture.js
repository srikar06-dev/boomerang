"use strict";
// Capture flow: start session -> 2 photos -> upload straight to S3 -> submit -> show the decision.

const $ = (id) => document.getElementById(id);
const SLOTS = ["item", "serial"];
const HINTS = ["Photo 1 of 2: the item, the scale display and the code, all in frame.",
               "Photo 2 of 2: a sharp close-up of the serial label.",
               "Both photos taken. Check them, then submit."];
const state = { token: null, mode: "return", blobs: [], stream: null };

$("mode").addEventListener("change", () => {
  const staff = $("mode").value === "shipout";
  show($("key-wrap"), staff);
  $("title").textContent = staff ? "Record a ship-out" : "Start a return";
  if (staff) $("key").value = store.get("boomerang_key");
});

$("start").addEventListener("click", async () => {
  $("start-error").textContent = "";
  const order = $("order").value.trim();
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(order)) { $("start-error").textContent = "Enter a valid order ID first."; return; }
  state.mode = $("mode").value;
  if (state.mode === "shipout") store.set("boomerang_key", $("key").value.trim());
  $("start").disabled = true;
  try {
    const s = await api("/session", { method: "POST", body: { order_id: order, purpose: state.mode }, staff: state.mode === "shipout" });
    state.token = s.token;
    state.blobs = [];
    $("code").textContent = s.code;
    for (const id of ["code-title", "code", "code-hint"]) show($(id), !!s.code_required);
    show($("serial-wrap"), state.mode === "shipout");
    show($("step-start"), false);
    show($("step-capture"), true);
    refresh();
    await startCamera();
  } catch (e) {
    $("start-error").textContent = e.message;
  } finally {
    $("start").disabled = false;
  }
});

async function startCamera() {
  const live = navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.isSecureContext;
  if (live) {
    try {
      state.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 } }, audio: false });
      $("video").srcObject = state.stream;
      show($("video"), true);
      return;
    } catch { /* permission denied or no camera: fall through */ }
  }
  show($("no-camera"), true);
}

function stopCamera() {
  if (state.stream) state.stream.getTracks().forEach((t) => t.stop());
  state.stream = null;
  $("video").srcObject = null;
  show($("video"), false);
}

// Draw to a canvas and export a JPEG no larger than 1280 px on the long side.
function toJpeg(source, w, h) {
  const scale = Math.min(1, 1280 / Math.max(w, h));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(w * scale);
  canvas.height = Math.round(h * scale);
  canvas.getContext("2d").drawImage(source, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Could not read the photo."))), "image/jpeg", 0.85));
}

async function addShot(blob) {
  if (state.blobs.length >= 2) return;
  const img = $("shot-" + SLOTS[state.blobs.length]);
  if (img.src) URL.revokeObjectURL(img.src);
  img.src = URL.createObjectURL(blob);
  show(img, true);
  state.blobs.push(blob);
  refresh();
}

$("shoot").addEventListener("click", async () => {
  $("capture-error").textContent = "";
  try {
    if (state.stream) {
      const v = $("video");
      if (!v.videoWidth) throw new Error("The camera is not ready yet. Try again in a second.");
      await addShot(await toJpeg(v, v.videoWidth, v.videoHeight));
    } else {
      $("file").click();
    }
  } catch (e) { $("capture-error").textContent = e.message; }
});

$("file").addEventListener("change", async () => {
  const file = $("file").files[0];
  $("file").value = "";
  if (!file) return;
  try {
    const bitmap = await createImageBitmap(file);
    await addShot(await toJpeg(bitmap, bitmap.width, bitmap.height));
  } catch { $("capture-error").textContent = "That file could not be read as a photo."; }
});

$("retake").addEventListener("click", () => {
  state.blobs = [];
  SLOTS.forEach((s) => show($("shot-" + s), false));
  refresh();
});

function refresh() {
  const n = state.blobs.length;
  $("hint").textContent = HINTS[n];
  $("shoot").disabled = n >= 2;
  $("retake").disabled = n === 0;
  $("submit").disabled = n < 2;
}

$("submit").addEventListener("click", async () => {
  $("capture-error").textContent = "";
  const weightText = $("weight").value.trim();
  const weight = weightText === "" ? null : Number(weightText);
  if (weight !== null && !(weight >= 0 && weight <= 100000)) { $("capture-error").textContent = "Weight must be between 0 and 100000 g."; return; }
  $("submit").disabled = true;
  $("submit").textContent = "Checking...";
  try {
    for (let i = 0; i < 2; i++) {
      const up = await api("/upload-url", { method: "POST", body: { token: state.token, slot: SLOTS[i] } });
      const put = await fetch(up.url, { method: "PUT", headers: { "Content-Type": up.content_type }, body: state.blobs[i] });
      if (!put.ok) throw new Error("Photo upload failed. Check the connection and try again.");
    }
    if (state.mode === "shipout") {
      const r = await api("/shipout", { method: "POST", staff: true,
        body: { token: state.token, weight_g: weight, serial: $("serial").value.trim() || null } });
      showShipout(r);
    } else {
      showResult(await api("/return", { method: "POST", body: { token: state.token, weight_g: weight } }));
    }
    stopCamera();
  } catch (e) {
    $("capture-error").textContent = e.message;
    $("submit").disabled = false;
  } finally {
    $("submit").textContent = "Submit";
  }
});

function showResult(r) {
  const known = DECISIONS.includes(r.decision) ? r.decision : "REVIEW";
  $("verdict").className = "verdict " + known;
  $("verdict-title").textContent = MEANING[known];
  $("verdict-sub").textContent = `Risk score ${Number(r.risk_score).toFixed(2)} · return ${r.return_id.slice(0, 8)}`;
  $("reasons").replaceChildren(...(r.reasons.length ? r.reasons : ["No issues found"]).map((x) => el("li", {}, x)));
  const d = r.disposition || {};
  $("disposition").textContent = d.action ? `Suggested next step: ${d.action.replaceAll("_", " ").toLowerCase()}` +
    (d.ship_back === false && d.action !== "HOLD_FOR_REVIEW" ? " (not worth shipping back)" : "") : "";
  show($("step-capture"), false);
  show($("step-result"), true);
}

function showShipout(r) {
  $("verdict").className = "verdict GREEN";
  $("verdict-title").textContent = "Ship-out recorded";
  const fp = r.fingerprint || {};
  $("verdict-sub").textContent = `Order ${r.order_id} · ${fp.weight_g ?? "no"} g · serial ${fp.serial || "none"}`;
  $("reasons").replaceChildren();
  $("disposition").textContent = "This unit's fingerprint is saved. Returns of this order are checked against it.";
  show($("step-capture"), false);
  show($("step-result"), true);
}

$("again").addEventListener("click", () => window.location.reload());
window.addEventListener("pagehide", stopCamera);
