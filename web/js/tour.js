/* First-time guided tour.
   A spotlight highlights one part of the app at a time with a short explanation and Previous / Next / Skip / Finish
   (keyboard: ← → and Esc). Steps a person cannot use (by permission) are left out. Progress is saved in the user's
   preferences on the server (tour_status, tour_step, tour_version), so it follows them across devices, with
   browser storage as a fallback; it resumes where it stopped, and "Take the tour again" (Help Centre, profile
   menu) restarts it. Raising TOUR_VERSION shows the tour again to everyone after a big change. */
import { $, api, state, store } from "./core.js";
import { t } from "./i18n.js";
import { can } from "./auth.js";

export const TOUR_VERSION = "1";
const STEPS = [
  { id: "welcome" },
  { id: "ask", sel: "#q", route: "#/ask" },
  { id: "case", sel: "#caseSel", route: "#/ask", perm: "cases.list" },
  { id: "scope", sel: "#scopeSel", route: "#/ask" },
  { id: "jur", sel: "#jurSel", route: "#/ask" },
  { id: "cases", sel: '.rail [data-nav="cases"]', perm: "cases.list" },
  { id: "library", sel: '.rail [data-nav="library"]' },
  { id: "bell", sel: "#bellLink", perm: "notifications.read" },
  { id: "profile", sel: "#profileMenu > summary" },
  { id: "help", sel: "#helpLink" },
  { id: "done" },
];

let tour = null;          // the running tour
let offeredThisLoad = false;

const visible = (el) => { if (!el) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
const wait = (ms) => new Promise((ok) => setTimeout(ok, ms));

async function save(status, step) {
  const values = { tour_status: status, tour_step: String(step), tour_version: TOUR_VERSION };
  store.set("tour", { status, step, version: TOUR_VERSION });
  try { state.prefs = await api("/api/prefs", { method: "PUT", body: { values }, retry: false }); } catch { /* browser copy kept */ }
}

function saved() {
  const p = state.prefs || {}, local = store.get("tour", {}) || {};
  const fromServer = p.tour_status !== undefined;
  return { status: fromServer ? p.tour_status : local.status, step: Number(fromServer ? p.tour_step : local.step) || 0,
           version: fromServer ? p.tour_version : local.version };
}

/** Called after every page change: starts (or resumes) the tour once for a signed-in user who has not finished it. */
export function maybeStartTour() {
  const s = state.session || {};
  if (tour || offeredThisLoad || !s.authenticated || !s.role || s.role === "guest" || document.body.classList.contains("authpage")) return;
  offeredThisLoad = true;
  const sv = saved();
  if ((sv.status === "completed" || sv.status === "skipped") && sv.version === TOUR_VERSION) return;
  startTour(sv.status === "in_progress" && sv.version === TOUR_VERSION ? sv.step : 0);
}

export function startTour(from = 0) {
  if (tour) return;
  const steps = STEPS.filter((s) => !s.perm || can(s.perm));
  const back = document.activeElement;
  const dim = document.createElement("div"); dim.className = "tour-dim";
  const spot = document.createElement("div"); spot.className = "tour-spot"; spot.setAttribute("aria-hidden", "true");
  const pop = document.createElement("div");
  pop.className = "tour-pop"; pop.setAttribute("role", "dialog"); pop.setAttribute("aria-modal", "true");
  pop.setAttribute("aria-labelledby", "tourTitle"); pop.setAttribute("aria-describedby", "tourBody");
  document.body.append(dim, spot, pop);
  tour = { steps, i: Math.min(Math.max(0, from), steps.length - 1), dim, spot, pop, back, target: null };
  document.addEventListener("keydown", onKey, true);
  window.addEventListener("resize", place);
  document.addEventListener("scroll", place, true);
  show();
}

function end(status) {
  if (!tour) return;
  const { dim, spot, pop, back, i } = tour;
  document.removeEventListener("keydown", onKey, true);
  window.removeEventListener("resize", place);
  document.removeEventListener("scroll", place, true);
  dim.remove(); spot.remove(); pop.remove();
  tour = null;
  save(status, status === "in_progress" ? i : 0);
  if (back && document.contains(back)) back.focus?.({ preventScroll: true });
}

async function show() {
  const tr = tour; if (!tr) return;
  const step = tr.steps[tr.i];
  if (step.route && location.hash.split("?")[0] !== step.route) location.hash = step.route;
  let el = step.sel ? document.querySelector(step.sel) : null;
  for (let n = 0; step.sel && !visible(el) && n < 30; n++) { await wait(100); if (tour !== tr) return; el = document.querySelector(step.sel); }
  if (!visible(el)) el = null;
  if (el) el.scrollIntoView({ block: "center", inline: "nearest" });
  tr.target = el;
  const last = tr.i === tr.steps.length - 1;
  tr.pop.innerHTML = "";
  const head = document.createElement("div"); head.className = "tour-count";
  head.textContent = t("tour.step", { n: tr.i + 1, total: tr.steps.length });
  const title = document.createElement("h2"); title.id = "tourTitle"; title.tabIndex = -1; title.textContent = t(`tour.${step.id}_title`);
  const body = document.createElement("p"); body.id = "tourBody"; body.textContent = t(`tour.${step.id}_body`);
  const bar = document.createElement("div"); bar.className = "tour-bar";
  const btn = (label, cls, fn, disabled = false) => {
    const b = document.createElement("button"); b.type = "button"; b.className = cls; b.textContent = label; b.disabled = disabled; b.onclick = fn; return b;
  };
  const skip = btn(t("tour.skip"), "link-btn tour-skip", () => end("skipped"));
  const prev = btn(t("tour.prev"), "btn btn-ghost", () => move(-1), tr.i === 0);
  const next = btn(last ? t("tour.finish") : t("tour.next"), "btn btn-saffron", () => (last ? end("completed") : move(1)));
  const spacer = document.createElement("span"); spacer.className = "spacer";
  bar.append(...(last ? [] : [skip]), spacer, prev, next);
  tr.pop.append(head, title, body, bar);
  tr.pop.classList.toggle("tour-center", !el);
  tr.dim.classList.toggle("on", !el);
  tr.spot.hidden = !el;
  place();
  title.focus({ preventScroll: true });
  save("in_progress", tr.i);
}

function move(d) {
  if (!tour) return;
  tour.i = Math.min(Math.max(0, tour.i + d), tour.steps.length - 1);
  show();
}

function place() {
  if (!tour) return;
  const { target, spot, pop } = tour;
  if (!target) { pop.style.left = ""; pop.style.top = ""; return; }
  const r = target.getBoundingClientRect(), pad = 6;
  Object.assign(spot.style, { left: `${r.left - pad}px`, top: `${r.top - pad}px`, width: `${r.width + 2 * pad}px`, height: `${r.height + 2 * pad}px` });
  const w = pop.offsetWidth, h = pop.offsetHeight, gap = 14, vw = window.innerWidth, vh = window.innerHeight;
  let top, left;
  if (r.bottom + gap + h <= vh) { top = r.bottom + gap; left = r.left; }                      // below
  else if (r.top - gap - h >= 0) { top = r.top - gap - h; left = r.left; }                    // above
  else if (r.right + gap + w <= vw) { left = r.right + gap; top = r.top; }                    // right (side rail)
  else { left = (vw - w) / 2; top = (vh - h) / 2; }                                           // centre
  pop.style.left = `${Math.max(12, Math.min(left, vw - w - 12))}px`;
  pop.style.top = `${Math.max(12, Math.min(top, vh - h - 12))}px`;
}

function onKey(e) {
  if (!tour) return;
  if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); end("skipped"); return; }
  if (e.key === "ArrowRight" && !e.target.closest?.("input, textarea, select")) { e.preventDefault(); if (tour.i < tour.steps.length - 1) move(1); else end("completed"); return; }
  if (e.key === "ArrowLeft" && !e.target.closest?.("input, textarea, select")) { e.preventDefault(); move(-1); return; }
  if (e.key === "Tab") {   // keep keyboard focus inside the tour card
    const f = [...tour.pop.querySelectorAll("button:not([disabled]), [tabindex='-1']")];
    const first = f[0], lastEl = f[f.length - 1];
    if (!tour.pop.contains(document.activeElement)) { e.preventDefault(); first?.focus(); }
    else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); lastEl.focus(); }
    else if (!e.shiftKey && document.activeElement === lastEl) { e.preventDefault(); first.focus(); }
  }
}
