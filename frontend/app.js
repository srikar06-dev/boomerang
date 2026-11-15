// Shared helpers for the Boomerang pages. Plain JS, no libraries.
// Text from the server is always inserted with textContent, never as HTML.
"use strict";

const store = {
  get(k) { try { return sessionStorage.getItem(k) || ""; } catch { return ""; } },
  set(k, v) { try { sessionStorage.setItem(k, v); } catch { /* private mode: keep going */ } },
};

// The API is the same site that served this page, unless staff typed another address in Settings.
function apiBase() {
  return (store.get("boomerang_api") || window.location.origin).replace(/\/+$/, "");
}

async function api(path, { method = "GET", body, staff = false } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (staff) headers["X-Station-Key"] = store.get("boomerang_key");
  let res;
  try {
    res = await fetch(apiBase() + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new Error("Cannot reach the Boomerang server. Is it running?");
  }
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    const detail = data && typeof data.detail === "string" ? data.detail : `Request failed (${res.status})`;
    throw new Error(detail);
  }
  return data;
}

// el("td", {class: "muted"}, "text", childNode, ...)
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v; else node.setAttribute(k, v);
  }
  for (const c of children) node.append(c instanceof Node ? c : document.createTextNode(String(c ?? "")));
  return node;
}

function badge(decision) { return el("span", { class: `badge ${DECISIONS.includes(decision) ? decision : ""}` }, decision); }
const DECISIONS = ["GREEN", "YELLOW", "RED", "REVIEW"];
const MEANING = {
  GREEN: "Instant refund",
  YELLOW: "Refund after receipt and spot check",
  RED: "Hold: a person must confirm",
  REVIEW: "Needs human review",
};
function money(n) { return "$" + Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 2 }); }
function when(iso) { const d = new Date(iso); return isNaN(d) ? "" : d.toLocaleString(); }
function show(node, on) { node.classList.toggle("hidden", !on); }

// Staff pages: the station key lives in a small chip in the top bar. Typed once per browser tab
// (sessionStorage), then shown as "Connected" with a Change button.
function setupStaffBar(onReady) {
  const key = document.getElementById("key");
  const connect = document.getElementById("connect");
  const ok = document.getElementById("key-ok");
  const change = document.getElementById("key-change");
  const connected = (on) => {
    [key, connect].forEach((n) => n && n.classList.toggle("hidden", on));
    [ok, change].forEach((n) => n && n.classList.toggle("hidden", !on));
  };
  key.value = store.get("boomerang_key");
  const go = () => {
    const v = key.value.trim();
    if (!v) return;
    store.set("boomerang_key", v);
    connected(true);
    onReady();
  };
  connect.addEventListener("click", go);
  key.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
  if (change) change.addEventListener("click", () => { connected(false); key.select(); key.focus(); });
  // A rejected key puts the field back so it can be fixed.
  window.addEventListener("boomerang:badkey", () => connected(false));
  if (key.value) {
    go();
  } else {
    connected(false);
    // In demo mode the key is literally "demo" — auto-connect so the dashboard loads without manual input.
    fetch(apiBase() + "/health").then(r => r.json()).then(h => {
      if (h.demo_mode && !key.value) { key.value = "demo"; go(); }
    }).catch(() => { /* health check failed: leave the key field for manual entry */ });
  }
}

// Call after a failed staff request: if the key was refused, reopen the key field.
function keyProblem(message) {
  if (/station key/i.test(message || "")) window.dispatchEvent(new Event("boomerang:badkey"));
}
