/* Help Centre: getting-started guides, FAQs and troubleshooting (static, translatable content in
   /static/help/<lang>.json), instant search in the browser (no AI call), "Report a problem" to the organisation's
   administrators, and "Take the tour again". Deep link to one article: #/help?a=<article id>. */
import { $, $$, api, crumbs, html, markdown, mount, raw, spinner, state, toast } from "./core.js";
import { lang, t } from "./i18n.js";
import { startTour } from "./tour.js";

const SECTION_TITLE = { start: "help.sec_start", faq: "help.sec_faq", trouble: "help.sec_trouble" };
const TOPICS = ["sign_in", "ai_answers", "documents", "drafting", "calendar", "other"];
const cache = {};

async function content() {
  const code = lang() === "hi" ? "hi" : "en";
  if (!cache[code]) {
    const r = await fetch(`/static/help/${code}.json`, { credentials: "same-origin" });
    if (!r.ok) throw new Error(t("help.load_failed"));
    cache[code] = await r.json();
  }
  return cache[code];
}

const words = (s) => s.toLowerCase().split(/\s+/).filter(Boolean);

export async function viewHelp(main, r) {
  crumbs([[t("help.title")]]);
  mount(main, spinner());
  const data = await content();
  const s = state.session || {};
  const signedIn = Boolean(s.authenticated && s.role && s.role !== "guest");
  const wanted = r.q.get("a") || "";
  mount(main, html`<div class="help">
    <h1 class="page-title">${t("help.title")}</h1>
    <p class="page-lead">${t("help.lead")}</p>
    <div class="help-tools">
      <form class="sec-search help-search" role="search" id="helpSearch">${raw('<svg class="ic ic-s" aria-hidden="true"><use href="#i-search"/></svg>')}
        <input type="search" id="helpQ" placeholder="${t("help.search_ph")}" aria-label="${t("help.search_ph")}" autocomplete="off"></form>
      ${signedIn ? html`<button type="button" class="btn btn-ghost" id="helpTour" data-tip="${t("tour.restart_tip")}">${t("tour.restart")}</button>` : ""}
      <a class="btn btn-ghost" href="#report">${t("help.sec_contact")}</a>
    </div>
    <p class="small muted" id="helpCount" aria-live="polite"></p>
    ${data.sections.map((sec) => html`<section class="help-sec" data-sec="${sec.id}" aria-labelledby="hs-${sec.id}">
      <h2 id="hs-${sec.id}">${t(SECTION_TITLE[sec.id] || sec.id)}</h2>
      ${sec.items.map((it) => html`<details class="help-item" id="${it.id}" data-text="${`${it.q} ${it.a}`.toLowerCase()}" ${it.id === wanted ? raw("open") : ""}>
        <summary>${it.q}</summary><div class="md help-body">${markdown(it.a)}</div></details>`)}
    </section>`)}
    <section class="help-sec card help-report" id="report" aria-labelledby="hs-report"><div class="card-b stack">
      <h2 id="hs-report">${t("help.sec_contact")}</h2>
      ${signedIn ? html`<p class="small muted">${t("help.report_lead")}</p>
        <form id="reportForm" class="stack">
          <label>${t("help.topic")} <select name="topic">${TOPICS.map((k) => html`<option value="${k}">${t(`help.topic_${k}`)}</option>`)}</select></label>
          <label>${t("help.message")} <textarea name="message" rows="4" minlength="5" maxlength="2000" required></textarea></label>
          <div><button class="btn btn-saffron" type="submit">${t("help.send")}</button></div>
        </form>` : html`<p>${t("help.sign_in_to_report")} <a href="#/login">${t("login.title")}</a></p>`}
    </div></section>
  </div>`);

  // Instant search over every article (titles and text), no AI call.
  const q = $("#helpQ"), count = $("#helpCount");
  const filter = () => {
    const ws = words(q.value);
    let shown = 0;
    $$(".help-item", main).forEach((d) => {
      const hit = ws.every((w) => d.dataset.text.includes(w));
      d.hidden = !hit; if (hit) shown++;
      if (ws.length && hit) d.open = true;
    });
    $$(".help-sec[data-sec]", main).forEach((sec) => { sec.hidden = !$$(".help-item:not([hidden])", sec).length; });
    count.textContent = ws.length ? (shown ? t("help.results", { n: shown }) : t("help.no_results", { q: q.value.trim() })) : "";
  };
  q.addEventListener("input", filter);
  $("#helpSearch").onsubmit = (e) => { e.preventDefault(); filter(); };
  if ($("#helpTour")) $("#helpTour").onclick = () => startTour(0);
  main.querySelector('a[href="#report"]').onclick = (e) => { e.preventDefault(); $("#report").scrollIntoView({ block: "start" }); $("#report textarea, #report a")?.focus(); };

  const form = $("#reportForm");
  if (form) form.onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const btn = form.querySelector("button[type=submit]"); btn.disabled = true;
    try {
      const r = await api("/api/support", { method: "POST", body: { topic: fd.get("topic"), message: String(fd.get("message") || "").trim(), page: state.prevRoute || "" } });
      toast(r.delivered ? t("help.sent") : t("help.sent_none"));
      form.reset();
    } catch (err) { toast(err.message, true); } finally { btn.disabled = false; }
  };

  if (wanted && $(`#${CSS.escape(wanted)}`)) {
    const el = $(`#${CSS.escape(wanted)}`);
    el.scrollIntoView({ block: "center" });
    el.querySelector("summary").focus({ preventScroll: true });
  }
}
