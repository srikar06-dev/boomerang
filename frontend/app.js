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

// Staff pages: wire up the key (and optional API address) fields.
function setupStaffBar(onReady) {
  const key = document.getElementById("key");
  const apiField = document.getElementById("api");
  key.value = store.get("boomerang_key");
  if (apiField) apiField.value = store.get("boomerang_api");
  document.getElementById("connect").addEventListener("click", () => {
    store.set("boomerang_key", key.value.trim());
    if (apiField) store.set("boomerang_api", apiField.value.trim());
    onReady();
  });
  if (key.value) onReady();
}
