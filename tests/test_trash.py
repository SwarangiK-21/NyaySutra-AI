"""Trash (recycle bin) tests (offline, synthetic data): deleting moves cases, documents, drafts and calendar entries
to the Trash, hides them everywhere (lists, search, AI retrieval, the vector index), restores them exactly, lets only
the right people restore or delete for good, and purges them after TRASH_DAYS."""
from __future__ import annotations

from datetime import datetime, timedelta

from nyaya import config, db, llm, retention, trash
from nyaya.vectorindex import index
from test_reliability import wait_job
from test_security import fake, new_case, person, signed_in, upload  # noqa: F401


def _items(c):
    r = c.get("/api/trash")
    assert r.status_code == 200, r.text
    return {(i["kind"], i["id"]): i for i in r.json()["items"]}


def _found(c, q="deposit"):
    return [r for r in c.get(f"/api/search?q={q}").json()["results"] if r["type"] == "document"]


def _event(c, **kw):
    body = {"title": "Hearing in Asha Rao v. Ramesh Kumar", "kind": "hearing", "event_date": "2099-03-10",
            "event_time": "11:00", "timezone": "Asia/Kolkata", "reminders": ["1d", "7d"], **kw}
    r = c.post("/api/calendar/events", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_trashed_case_disappears_everywhere_and_restores_with_its_contents(fake):
    person(fake, "adv@example.com", "advocate")
    a = signed_in("adv@example.com")
    case_id = new_case(a)
    a.post(f"/api/cases/{case_id}/notes", json={"content": "Strategy note"})
    doc = upload(a, case_id)
    assert _found(a)

    r = a.delete(f"/api/cases/{case_id}")
    assert r.status_code == 200 and r.json()["trash"] is True
    assert case_id not in {c["id"] for c in a.get("/api/cases").json()["cases"]}
    assert a.get(f"/api/cases/{case_id}").status_code == 404
    assert a.get(f"/api/documents/{doc['id']}/file").status_code == 404        # its files go with it
    assert doc["id"] not in {d["id"] for d in a.get("/api/documents").json()["documents"]}
    assert not _found(a)                                                         # and its passages
    item = _items(a)[("case", case_id)]
    assert item["deleted_by_name"] == "you" and item["purge_at"] and item["can_purge"] is False
    assert a.delete(f"/api/cases/{case_id}").status_code == 404                  # not twice

    r = a.post(f"/api/trash/case/{case_id}/restore")
    assert r.status_code == 200 and r.json()["open"] == f"#/cases/{case_id}"
    c = a.get(f"/api/cases/{case_id}").json()
    assert c["notes"] and c["notes"][0]["content"] == "Strategy note"
    assert a.get(f"/api/documents/{doc['id']}/file").status_code == 200
    assert _found(a) and ("case", case_id) not in _items(a)
    acts = [x["action"] for x in db.conn().execute("SELECT action FROM audit_log ORDER BY id")]
    assert "case.trash" in acts and "case.restore" in acts


def test_trashed_document_leaves_search_and_the_vector_index_and_comes_back(fake):
    person(fake, "adv@example.com", "advocate")
    a = signed_in("adv@example.com")
    case_id = new_case(a)
    doc = upload(a, case_id)
    in_index = lambda: doc["id"] in set(index.doc.tolist())   # noqa: E731
    assert in_index() and _found(a)

    assert a.delete(f"/api/documents/{doc['id']}").status_code == 200
    assert not in_index() and not _found(a)
    assert a.get(f"/api/documents/{doc['id']}").status_code == 404
    assert a.get(f"/api/documents?case_id={case_id}").json()["documents"] == []
    assert a.get(f"/api/cases").json()["cases"][0]["n_docs"] == 0
    assert ("document", doc["id"]) in _items(a)

    assert a.post(f"/api/trash/document/{doc['id']}/restore").status_code == 200
    assert in_index() and _found(a)
    assert a.get(f"/api/documents/{doc['id']}").json()["status"] == "ready"


def test_trashed_draft_is_hidden_and_restorable(fake, monkeypatch):
    person(fake, "adv@example.com", "advocate")
    a = signed_in("adv@example.com")
    case_id = new_case(a)
    monkeypatch.setattr(llm, "chat", lambda *x, **k: "DRAFT — FOR REVIEW\n\nNotice to pay the deposit.")
    job = a.post("/api/drafts/generate", json={"doc_type": "notice_ni_138", "forum": "none", "case_id": case_id}).json()
    d = wait_job(a, job["id"])["result"]
    assert a.delete(f"/api/drafts/{d['id']}").status_code == 200
    assert a.get(f"/api/drafts/{d['id']}").status_code == 404
    assert d["id"] not in {x["id"] for x in a.get("/api/drafts").json()["drafts"]}
    assert ("draft", d["id"]) in _items(a)
    assert a.post(f"/api/trash/draft/{d['id']}/restore").status_code == 200
    assert a.get(f"/api/drafts/{d['id']}").status_code == 200


def test_trashed_event_withdraws_its_reminders_and_restore_schedules_them_again(fake):
    person(fake, "adv@example.com", "advocate")
    a = signed_in("adv@example.com")
    ev = _event(a)
    pending = lambda: db.conn().execute("SELECT COUNT(*) FROM event_reminders WHERE event_id=? AND status='pending'",  # noqa: E731
                                        (ev["id"],)).fetchone()[0]
    assert pending() == 2
    assert a.delete(f"/api/calendar/events/{ev['id']}").status_code == 200
    assert pending() == 0
    assert a.get(f"/api/calendar/events/{ev['id']}").status_code == 404
    assert not a.get("/api/calendar/events?start=2099-03-01&end=2099-03-31").json()["events"]
    assert a.post(f"/api/trash/event/{ev['id']}/restore").status_code == 200
    assert pending() == 2
    assert a.get(f"/api/calendar/events/{ev['id']}").status_code == 200


def test_only_the_right_people_see_restore_or_delete_for_good(fake):
    person(fake, "adv@example.com", "advocate")
    person(fake, "col@example.com", "advocate")
    person(fake, "admin@example.com", "admin")
    a, col, admin = (signed_in(e) for e in ("adv@example.com", "col@example.com", "admin@example.com"))
    case_id = new_case(a)
    ev = _event(a)
    a.delete(f"/api/calendar/events/{ev['id']}")
    a.delete(f"/api/cases/{case_id}")
    # A colleague who is not on the case, and anyone but the owner of a calendar entry, see nothing.
    assert _items(col) == {}
    assert col.post(f"/api/trash/case/{case_id}/restore").status_code == 404
    assert col.post(f"/api/trash/event/{ev['id']}/restore").status_code == 404
    # Lawyers cannot delete for good; administrators can, but only what they can see (not a private calendar).
    assert a.delete(f"/api/trash/case/{case_id}").status_code == 403
    assert a.post("/api/trash/empty").status_code == 403
    seen = _items(admin)
    assert ("case", case_id) in seen and ("event", ev["id"]) not in seen and seen[("case", case_id)]["can_purge"]
    assert admin.delete(f"/api/trash/event/{ev['id']}").status_code == 404
    assert admin.delete(f"/api/trash/case/{case_id}").status_code == 200
    with db.system():
        assert db.conn().execute("SELECT COUNT(*) FROM cases WHERE id=?", (case_id,)).fetchone()[0] == 0
    assert a.post(f"/api/trash/case/{case_id}/restore").status_code == 404
    assert ("event", ev["id"]) in _items(a)                                      # untouched


def test_admin_can_trash_and_restore_a_case_they_are_not_on(fake):
    person(fake, "adv@example.com", "advocate")
    person(fake, "admin@example.com", "admin")
    a, admin = signed_in("adv@example.com"), signed_in("admin@example.com")
    case_id = new_case(a)
    assert admin.delete(f"/api/cases/{case_id}").status_code == 200
    assert a.get(f"/api/cases/{case_id}").status_code == 404
    assert ("case", case_id) in _items(a)                                        # the owner can still restore it
    assert admin.post(f"/api/trash/case/{case_id}/restore").status_code == 200
    assert a.get(f"/api/cases/{case_id}").status_code == 200


def test_items_older_than_trash_days_are_purged_by_the_daily_job(fake):
    person(fake, "adv@example.com", "advocate")
    a = signed_in("adv@example.com")
    old_case, new_case_id = new_case(a, "Old matter"), new_case(a, "Recent matter")
    doc = upload(a, new_case_id)
    a.delete(f"/api/cases/{old_case}")
    a.delete(f"/api/cases/{new_case_id}")
    long_ago = (datetime.now() - timedelta(days=config.TRASH_DAYS + 1)).isoformat(timespec="seconds")
    with db.system(), db.tx() as c:
        c.execute("UPDATE cases SET deleted_at=? WHERE id=?", (long_ago, old_case))
    assert trash.purge_expired(dry_run=True)["case"] == 1
    res = retention.run()
    assert res["trash"]["case"] == 1
    with db.system():
        left = {r["id"] for r in db.conn().execute("SELECT id FROM cases")}
        assert old_case not in left and new_case_id in left
        assert db.conn().execute("SELECT COUNT(*) FROM documents WHERE id=?", (doc["id"],)).fetchone()[0] == 1
    assert set(_items(a)) == {("case", new_case_id)}
