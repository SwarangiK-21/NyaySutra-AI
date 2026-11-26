/* Shared accessible UI: one tooltip for the whole app.
   Any element with data-tip="…" (or an old-style title="…", which is upgraded on first use) gets a tooltip that
   appears on mouse hover AND keyboard focus, closes with Esc, is announced through aria-describedby, and never
   holds information found nowhere else (the element keeps its own label). */
import { $ } from "./core.js";

const SEL = "[data-tip], [title]:not(svg *):not(iframe)";

export function initTooltips() {
  if ($("#tip")) return;
  const tip = document.createElement("div");
  tip.id = "tip"; tip.className = "tip"; tip.setAttribute("role", "tooltip"); tip.hidden = true;
  document.body.appendChild(tip);
  let target = null, timer = 0;

  // Move a native title into data-tip so the browser's own (mouse-only, unstyled) tooltip does not also appear.
  // An element that was named only by its title keeps that name as its aria-label.
  const upgrade = (el) => {
    if (!el.hasAttribute("title")) return;
    const v = el.getAttribute("title");
    if (v && !el.dataset.tip) el.dataset.tip = v;
    if (v && !el.getAttribute("aria-label") && !el.textContent.trim()) el.setAttribute("aria-label", v);
    el.removeAttribute("title");
  };
  const place = () => {
    if (!target) return;
    const r = target.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight, gap = 8;
    let top = r.bottom + gap;
    if (top + h > window.innerHeight - 4) top = r.top - h - gap;
    let left = r.left + r.width / 2 - w / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - w - 8));
    tip.style.top = `${Math.max(4, top)}px`; tip.style.left = `${left}px`;
  };
  const show = (el) => {
    upgrade(el);
    const text = (el.dataset.tip || "").trim();
    if (!text) return;
    hide();
    target = el; tip.textContent = text; tip.hidden = false;
    const ids = (el.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
    if (!ids.includes("tip")) el.setAttribute("aria-describedby", [...ids, "tip"].join(" "));
    place();
  };
  function hide() {
    clearTimeout(timer);
    if (target) {
      const ids = (target.getAttribute("aria-describedby") || "").split(/\s+/).filter((x) => x && x !== "tip");
      if (ids.length) target.setAttribute("aria-describedby", ids.join(" ")); else target.removeAttribute("aria-describedby");
    }
    target = null; tip.hidden = true;
  }

  document.addEventListener("mouseover", (e) => {
    const el = e.target.closest?.(SEL);
    if (el === target) return;
    clearTimeout(timer);
    if (!el) { hide(); return; }
    upgrade(el);
    timer = setTimeout(() => show(el), 350);
  });
  document.addEventListener("focusin", (e) => {
    const el = e.target.closest?.(SEL);
    if (el && el.matches(":focus-visible")) show(el); else hide();
  });
  document.addEventListener("focusout", () => hide());
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && target) hide(); });
  document.addEventListener("scroll", () => hide(), true);
  window.addEventListener("resize", () => hide());
}
