/* Trash — deleted cases, case documents, drafts and calendar entries, kept for 30 days (server: nyaya/trash.py).
   Everyone sees and restores what they may restore; administrators can also delete for good. */
import { $, $$, api, confirmDialog, crumbs, fmtDate, fmtDateTime, html, mount, spinner, toast } from "./core.js";
import { t } from "./i18n.js";

const ICON = { case: "📁", document: "📄", draft: "📝", event: "📅" };
const daysLeft = (iso) => Math.max(0, Math.ceil((new Date(iso) - new Date()) / 864e5));

export async function viewTrash(main) {
  crumbs([[t("nav.cases_short"), "#/cases"], [t("trash.title")]]);
  mount(main, html`<div id="trashBody">${spinner()}</div>`);
  const load = async () => {
    let res;
    try { res = await api("/api/trash"); } catch (e) { mount($("#trashBody"), html`<div class="notice notice-red">${e.message}</div>`); return; }
    const { items, days, can_purge: canPurge } = res;
    mount($("#trashBody"), html`<div class="row" style="justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap">
        <p class="page-lead" style="margin:0">${t("trash.lead", { days })}</p>
        ${canPurge && items.length ? html`<button type="button" class="btn btn-ghost btn-sm danger" id="trashEmpty">${t("trash.empty")}</button>` : ""}</div>
      ${items.length ? html`<div class="card" style="margin-top:12px"><div class="table-wrap"><table class="gov"><thead><tr>
          <th>${t("trash.item")}</th><th>${t("trash.deleted")}</th><th>${t("trash.left")}</th><th></th></tr></thead><tbody>
        ${items.map((i) => html`<tr>
          <td><span aria-hidden="true">${ICON[i.kind] || "•"}</span> <strong>${i.title}</strong>
            <div class="small muted">${t(`trash.kind_${i.kind}`)}${i.detail ? html` · ${i.detail}` : ""}</div></td>
          <td class="small">${fmtDateTime(i.deleted_at)}${i.deleted_by_name ? html`<br><span class="muted">${i.deleted_by_name === "you" ? t("trash.by_you") : t("trash.by", { name: i.deleted_by_name })}</span>` : ""}</td>
          <td class="small"><span class="chip ${daysLeft(i.purge_at) <= 3 ? "chip-warn" : ""}" title="${fmtDate(i.purge_at)}">${t("trash.days_left", { n: daysLeft(i.purge_at) })}</span></td>
          <td style="white-space:nowrap"><button type="button" class="btn btn-sm" data-restore="${i.kind}/${i.id}">${t("trash.restore")}</button>
            ${i.can_purge ? html`<button type="button" class="btn btn-ghost btn-sm danger" data-purge="${i.kind}/${i.id}">${t("trash.purge")}</button>` : ""}</td></tr>`)}
        </tbody></table></div></div>` : html`<div class="empty" style="margin-top:12px">${t("trash.none")}</div>`}`);
    const path = (v) => v.split("/").map(encodeURIComponent).join("/");
    $$("[data-restore]", main).forEach((b) => { b.onclick = async () => {
      b.disabled = true;
      try {
        const r = await api(`/api/trash/${path(b.dataset.restore)}/restore`, { method: "POST" });
        toast(t("trash.restored")); load();
        if (r.open && r.kind === "case") location.hash = r.open;
      } catch (e) { toast(e.message, true); b.disabled = false; }
    }; });
    $$("[data-purge]", main).forEach((b) => { b.onclick = async () => {
      if (!await confirmDialog(t("trash.purge_title"), t("trash.purge_body"), t("trash.purge"))) return;
      try { await api(`/api/trash/${path(b.dataset.purge)}`, { method: "DELETE" }); toast(t("trash.purged")); load(); } catch (e) { toast(e.message, true); }
    }; });
    const empty = $("#trashEmpty");
    if (empty) empty.onclick = async () => {
      if (!await confirmDialog(t("trash.empty_title"), t("trash.empty_body", { n: items.length }), t("trash.empty"))) return;
      try { const r = await api("/api/trash/empty", { method: "POST" }); toast(t("trash.emptied", { n: r.deleted })); load(); } catch (e) { toast(e.message, true); }
    };
  };
  load();
}
