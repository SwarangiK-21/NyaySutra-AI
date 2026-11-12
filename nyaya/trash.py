"""Trash (recycle bin): deleting a case, case document, draft or calendar event moves it here first.

* Moving to the Trash hides the item at once from every list, search and AI answer:
    - a case: the access checks (nyaya/authz.py, and private.case_access in Supabase) give nobody access to a case
      with deleted_at set, so its notes, files, passages, drafts and chats go with it;
    - a document: status 'trashed' (only 'ready' documents are searched) and it leaves the in-memory vector index;
    - a draft or calendar event: deleted_at, filtered by their own queries; an event's pending reminders are withdrawn.
* Restore puts it back exactly as it was (a document returns to the vector index from its stored embeddings).
* After config.TRASH_DAYS (30) the daily retention job deletes it for good, files included (purge_expired).
* An administrator can delete an item permanently at once ("Delete forever", "Empty Trash"), e.g. for a client's
  erasure request.

Who may do what (checked here, then the change runs as system work, because once trashed the item is outside the
normal access rules):
    case       trash: case owner or organisation administrator   restore: the same
    document   trash/restore: case owner or advocate on a case that is not itself in the Trash
    draft      trash/restore: its author (personal draft) or the case team
    event      trash/restore: its owner (calendars are private)
    purge      administrators only, for items they can see in their Trash
Every step is in the audit log (*.trash, *.restore, *.purge); never the contents.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from . import authz, config, db

log = logging.getLogger("nyaya.trash")
KINDS = ("case", "document", "draft", "event")
_TRASHABLE_DOC = ("ready", "failed", "quarantined", "cancelled")


class TrashError(Exception):
    """400/409 — the message is safe to show."""


def _now() -> str:
    return db.now()


def purge_at(deleted_at: str | None) -> str | None:
    try:
        return (datetime.fromisoformat(deleted_at) + timedelta(days=config.TRASH_DAYS)).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return None


# ── Who may act on a trashed item (the normal checks no longer see it) ─────
def _case_row(case_id: str):
    with db.system():
        return db.conn().execute("SELECT id, org_id, title, deleted_at, deleted_by FROM cases WHERE id=?",
                                 (case_id,)).fetchone()


def _member_access(p: authz.Principal, case_id: str) -> str | None:
    with db.system():
        row = db.conn().execute("SELECT access FROM case_members WHERE case_id=? AND user_id=?",
                                (case_id, p.user_id)).fetchone()
    return authz._cap(p.role, row["access"]) if row else None


def _may_manage_case(p: authz.Principal, case) -> bool:
    if not p.signed_in or not case or case["org_id"] != p.org_id:
        return False
    return p.role == "admin" or _member_access(p, case["id"]) == "owner"


def _doc_row(doc_id: str):
    with db.system():
        return db.conn().execute("SELECT id, case_id, collection, title, filename, status, meta, deleted_at, deleted_by "
                                 "FROM documents WHERE id=?", (doc_id,)).fetchone()


def _may_manage_doc(p: authz.Principal, doc) -> bool:
    # The case must be live: a document of a trashed case comes back with its case.
    return bool(doc and doc["collection"] == "case" and doc["case_id"]
                and authz.can_case(p, doc["case_id"], "documents.delete"))


def _draft_row(draft_id: str):
    with db.system():
        return db.conn().execute("SELECT id, case_id, created_by, title, kind, deleted_at, deleted_by FROM drafts "
                                 "WHERE id=?", (draft_id,)).fetchone()


def _may_manage_draft(p: authz.Principal, d) -> bool:
    if not d or not p.can("drafting.use"):
        return False
    if d["case_id"]:
        return authz.can_case(p, d["case_id"], "drafts")
    return d["created_by"] == p.user_id


def _event_row(p: authz.Principal, event_id: str):
    with db.system():
        return db.conn().execute("SELECT * FROM calendar_events WHERE id=? AND owner_id=?",
                                 (event_id, p.user_id or "")).fetchone()


def _derived(doc_id: str) -> list[str]:
    with db.system():
        return [r["id"] for r in db.conn().execute(
            "SELECT id FROM documents WHERE meta->>'derived_from' = ?", (doc_id,))]


# ── Move to the Trash ────────────────────────────────────────────────────────
def trash_case(p: authz.Principal, case_id: str) -> None:
    case = _case_row(case_id)
    if not case or case["deleted_at"] or not _may_manage_case(p, case):
        raise authz.NotFound("Case not found")
    with db.system(), db.tx() as c:
        c.execute("UPDATE cases SET deleted_at=?, deleted_by=? WHERE id=? AND deleted_at IS NULL",
                  (_now(), p.user_id, case_id))
    db.audit("case.trash", "case", case_id)


def trash_document(p: authz.Principal, doc_id: str) -> None:
    from .vectorindex import index
    doc = _doc_row(doc_id)
    if not doc or doc["status"] == "trashed" or not _may_manage_doc(p, doc):
        raise authz.NotFound("Document not found")
    if doc["status"] not in _TRASHABLE_DOC:
        raise TrashError("This document is still being processed. Try again when it has finished.")
    if '"derived_from"' in (doc["meta"] or ""):
        raise TrashError("A translation or summary is removed together with its original document.")
    now = _now()
    ids = [doc_id, *_derived(doc_id)]
    with db.system(), db.tx() as c:
        for i in ids:
            row = c.execute("SELECT status, meta FROM documents WHERE id=?", (i,)).fetchone()
            if not row or row["status"] == "trashed":
                continue
            meta = json.loads(row["meta"] or "{}")
            meta["trashed_from"] = row["status"]   # restored to this status
            c.execute("UPDATE documents SET status='trashed', meta=?, deleted_at=?, deleted_by=? WHERE id=?",
                      (json.dumps(meta, ensure_ascii=False), now, p.user_id, i))
    for i in ids:
        index.remove_doc(i)
    db.audit("document.trash", "document", doc_id, case_id=doc["case_id"])


def trash_draft(p: authz.Principal, draft_id: str) -> None:
    d = _draft_row(draft_id)
    if not d or d["deleted_at"] or not _may_manage_draft(p, d):
        raise authz.NotFound("Draft not found")
    with db.system(), db.tx() as c:
        c.execute("UPDATE drafts SET deleted_at=?, deleted_by=? WHERE id=? AND deleted_at IS NULL",
                  (_now(), p.user_id, draft_id))
    db.audit("draft.trash", "draft", draft_id)


def trash_event(p: authz.Principal, event_id: str) -> None:
    ev = _event_row(p, event_id)
    if not ev or ev["deleted_at"]:
        raise authz.NotFound("Event not found")
    with db.system(), db.tx() as c:
        c.execute("UPDATE calendar_events SET deleted_at=?, deleted_by=? WHERE id=? AND owner_id=?",
                  (_now(), p.user_id, event_id, p.user_id))
        # Reminders that were not sent yet are withdrawn; restore schedules them again.
        c.execute("DELETE FROM event_reminders WHERE event_id=? AND status IN ('pending', 'skipped', 'failed')",
                  (event_id,))
    db.audit("calendar.trash", "event", event_id)


# ── List ─────────────────────────────────────────────────────────────────────
def _names(user_ids: set[str]) -> dict[str, str]:
    ids = sorted(u for u in user_ids if u)
    if not ids:
        return {}
    with db.system():
        return {r["user_id"]: r["display_name"] or r["email"] or "" for r in db.conn().execute(
            f"SELECT user_id, display_name, email FROM profiles WHERE user_id IN ({','.join('?' * len(ids))})", ids)}


def list_items(p: authz.Principal) -> list[dict]:
    """What the caller may restore, newest first."""
    if not p.signed_in:
        return []
    items: list[dict] = []
    with db.system():
        cases = db.conn().execute("SELECT id, org_id, title, client_name, court, deleted_at, deleted_by FROM cases "
                                  "WHERE deleted_at IS NOT NULL AND org_id=?", (p.org_id,)).fetchall()
    for c in cases:
        if _may_manage_case(p, c):
            items.append({"kind": "case", "id": c["id"], "title": c["title"],
                          "detail": " · ".join(x for x in (c["client_name"], c["court"]) if x),
                          "deleted_at": c["deleted_at"], "deleted_by": c["deleted_by"]})
    team = authz.team_case_ids(p)   # live cases only
    if team:
        ph = ",".join("?" * len(team))
        with db.system():
            docs = db.conn().execute(
                f"SELECT d.id, d.title, d.filename, d.case_id, d.deleted_at, d.deleted_by, c.title AS case_title "
                f"FROM documents d JOIN cases c ON c.id = d.case_id WHERE d.status='trashed' AND d.collection='case' "
                f"AND d.case_id IN ({ph}) AND d.meta->>'derived_from' IS NULL", team).fetchall()
        items += [{"kind": "document", "id": d["id"], "title": d["title"] or d["filename"],
                   "detail": d["case_title"], "case_id": d["case_id"],
                   "deleted_at": d["deleted_at"], "deleted_by": d["deleted_by"]} for d in docs]
    if p.can("drafting.use"):
        own = "(d.case_id IS NULL AND d.created_by = ?)" + (f" OR d.case_id IN ({','.join('?' * len(team))})" if team else "")
        with db.system():
            drafts = db.conn().execute(
                f"SELECT d.id, d.title, d.kind, d.case_id, d.deleted_at, d.deleted_by, c.title AS case_title "
                f"FROM drafts d LEFT JOIN cases c ON c.id = d.case_id WHERE d.deleted_at IS NOT NULL AND ({own})",
                (p.user_id, *team)).fetchall()
        items += [{"kind": "draft", "id": d["id"], "title": d["title"], "detail": d["case_title"] or "",
                   "subtype": d["kind"], "deleted_at": d["deleted_at"], "deleted_by": d["deleted_by"]} for d in drafts]
    with db.system():
        evs = db.conn().execute("SELECT id, title, kind, event_date, event_time, deleted_at, deleted_by "
                                "FROM calendar_events WHERE owner_id=? AND deleted_at IS NOT NULL", (p.user_id,)).fetchall()
    items += [{"kind": "event", "id": e["id"], "title": e["title"], "subtype": e["kind"],
               "detail": " ".join(x for x in (e["event_date"], e["event_time"] or "") if x),
               "deleted_at": e["deleted_at"], "deleted_by": e["deleted_by"]} for e in evs]
    names = _names({i["deleted_by"] for i in items})
    can_purge = p.can("trash.purge")
    for i in items:
        i["deleted_by_name"] = "you" if i["deleted_by"] == p.user_id else names.get(i["deleted_by"], "")
        i["deleted_by"] = None   # ids stay on the server
        i["purge_at"] = purge_at(i["deleted_at"])
        i["can_purge"] = can_purge
    return sorted(items, key=lambda i: i["deleted_at"] or "", reverse=True)


# ── Restore ──────────────────────────────────────────────────────────────────
def restore(p: authz.Principal, kind: str, item_id: str) -> dict:
    from .vectorindex import index
    if kind == "case":
        case = _case_row(item_id)
        if not case or not case["deleted_at"] or not _may_manage_case(p, case):
            raise authz.NotFound("Not in the Trash")
        with db.system(), db.tx() as c:
            c.execute("UPDATE cases SET deleted_at=NULL, deleted_by=NULL WHERE id=?", (item_id,))
        db.audit("case.restore", "case", item_id)
        return {"kind": kind, "id": item_id, "open": f"#/cases/{item_id}"}
    if kind == "document":
        doc = _doc_row(item_id)
        if not doc or doc["status"] != "trashed" or not _may_manage_doc(p, doc):
            raise authz.NotFound("Not in the Trash")
        ids = [item_id, *_derived(item_id)]
        with db.system():
            with db.tx() as c:
                for i in ids:
                    row = c.execute("SELECT status, meta FROM documents WHERE id=?", (i,)).fetchone()
                    if not row or row["status"] != "trashed":
                        continue
                    meta = json.loads(row["meta"] or "{}")
                    status = meta.pop("trashed_from", "ready")
                    c.execute("UPDATE documents SET status=?, meta=?, deleted_at=NULL, deleted_by=NULL WHERE id=?",
                              (status if status in _TRASHABLE_DOC else "ready", json.dumps(meta, ensure_ascii=False), i))
            for i in ids:
                index.add_doc_from_db(i)
        db.audit("document.restore", "document", item_id, case_id=doc["case_id"])
        return {"kind": kind, "id": item_id, "open": f"#/doc/{item_id}"}
    if kind == "draft":
        d = _draft_row(item_id)
        if not d or not d["deleted_at"] or not _may_manage_draft(p, d):
            raise authz.NotFound("Not in the Trash")
        with db.system(), db.tx() as c:
            c.execute("UPDATE drafts SET deleted_at=NULL, deleted_by=NULL WHERE id=?", (item_id,))
        db.audit("draft.restore", "draft", item_id)
        return {"kind": kind, "id": item_id, "open": f"#/drafting?draft={item_id}"}
    if kind == "event":
        from . import events
        ev = _event_row(p, item_id)
        if not ev or not ev["deleted_at"]:
            raise authz.NotFound("Not in the Trash")
        with db.system(), db.tx() as c:
            c.execute("UPDATE calendar_events SET deleted_at=NULL, deleted_by=NULL WHERE id=? AND owner_id=?",
                      (item_id, p.user_id))
            events._schedule(c, events._row(ev))
        db.audit("calendar.restore", "event", item_id)
        return {"kind": kind, "id": item_id, "open": "#/calendar"}
    raise TrashError("Unknown item type.")


# ── Delete for good ──────────────────────────────────────────────────────────
def _hard_delete(kind: str, item_id: str) -> bool:
    """Runs as system work; the caller has already checked the right to do it."""
    from . import cases, drafting, ingest
    with db.system():
        if kind == "case":
            return cases.delete_case(item_id)
        if kind == "document":
            return ingest.delete_document(item_id)
        if kind == "draft":
            return drafting.delete(item_id)
        if kind == "event":
            with db.tx() as c:
                c.execute("DELETE FROM event_reminders WHERE event_id=?", (item_id,))
                return c.execute("DELETE FROM calendar_events WHERE id=?", (item_id,)).rowcount > 0
    return False


def purge(p: authz.Principal, kind: str, item_id: str) -> None:
    """Delete one item from the Trash permanently (administrators)."""
    authz.require(p, "trash.purge")
    if kind not in KINDS:
        raise TrashError("Unknown item type.")
    if not any(i["kind"] == kind and i["id"] == item_id for i in list_items(p)):
        raise authz.NotFound("Not in the Trash")
    _hard_delete(kind, item_id)
    db.audit(f"{'calendar' if kind == 'event' else kind}.purge", kind, item_id)


def empty(p: authz.Principal) -> int:
    """Delete everything the caller sees in the Trash permanently (administrators)."""
    authz.require(p, "trash.purge")
    items = list_items(p)
    for i in items:
        _hard_delete(i["kind"], i["id"])
    db.audit("trash.empty", "trash", None, items=len(items))
    return len(items)


def purge_expired(now: datetime | None = None, dry_run: bool = False) -> dict:
    """Daily (nyaya/retention.py): delete what has been in the Trash for longer than TRASH_DAYS. System work."""
    cut = ((now or datetime.now()) - timedelta(days=config.TRASH_DAYS)).isoformat(timespec="seconds")
    out = {}
    with db.system():
        found = {
            "case": [r["id"] for r in db.conn().execute("SELECT id FROM cases WHERE deleted_at < ?", (cut,))],
            "document": [r["id"] for r in db.conn().execute(
                "SELECT id FROM documents WHERE status='trashed' AND deleted_at < ? AND meta->>'derived_from' IS NULL",
                (cut,))],
            "draft": [r["id"] for r in db.conn().execute("SELECT id FROM drafts WHERE deleted_at < ?", (cut,))],
            "event": [r["id"] for r in db.conn().execute("SELECT id FROM calendar_events WHERE deleted_at < ?", (cut,))],
        }
    for kind, ids in found.items():
        out[kind] = len(ids)
        if dry_run:
            continue
        for i in ids:
            try:
                _hard_delete(kind, i)
            except Exception as exc:   # one bad item must not stop the rest; it is retried tomorrow
                log.warning("Could not purge %s %s from the Trash: %s", kind, i, type(exc).__name__)
    if not dry_run and any(out.values()):
        with db.system():
            db.audit("trash.purge_expired", "trash", None, **out)
    return out
