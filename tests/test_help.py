"""Help Centre and onboarding (backend parts), offline: guided-tour progress saved in the user's preferences, and
"Report a problem" reaching only the reporter's own organisation's administrators."""
from __future__ import annotations

from nyaya import db
from test_security import fake, guest, person, signed_in  # noqa: F401


def test_tour_progress_is_saved_per_user_and_validated(fake):
    person(fake, "adv@example.com", "advocate")
    a = signed_in("adv@example.com")
    assert "tour_status" not in a.get("/api/prefs").json()                      # a new user has never seen the tour
    r = a.put("/api/prefs", json={"values": {"tour_status": "in_progress", "tour_step": "3", "tour_version": "1"}})
    assert r.status_code == 200 and r.json()["tour_status"] == "in_progress" and r.json()["tour_step"] == "3"
    assert a.put("/api/prefs", json={"values": {"tour_status": "completed"}}).json()["tour_status"] == "completed"
    for bad in ({"tour_status": "hacked"}, {"tour_step": "999"}, {"tour_version": "0"}):
        assert a.put("/api/prefs", json={"values": bad}).status_code == 400
    # Another user's progress is separate.
    person(fake, "col@example.com", "advocate")
    assert "tour_status" not in signed_in("col@example.com").get("/api/prefs").json()


def test_problem_reports_go_to_this_organisations_administrators_only(fake):
    with db.system(), db.tx() as c:
        c.execute("INSERT INTO organizations(id, name, created_at) VALUES('org_b', 'Other firm', ?)", (db.now(),))
    person(fake, "adv@example.com", "advocate")
    person(fake, "admin@example.com", "admin")
    person(fake, "other-admin@example.com", "admin", org="org_b")
    a, admin, other = (signed_in(e) for e in ("adv@example.com", "admin@example.com", "other-admin@example.com"))

    assert guest().post("/api/support", json={"message": "It does not work"}).status_code in (401, 403)
    assert a.post("/api/support", json={"message": "hi"}).status_code == 422                  # too short
    assert a.post("/api/support", json={"topic": "nonsense", "message": "Upload keeps failing"}).status_code == 422

    r = a.post("/api/support", json={"topic": "documents", "message": "Upload of a scanned PDF keeps failing.",
                                     "page": "#/cases/CASE-1<script>"})
    assert r.status_code == 200 and r.json()["delivered"] is True
    mine = admin.get("/api/notifications").json()["items"]
    report = next(n for n in mine if n["title"].startswith("Problem report from"))
    assert "documents" in report["title"] and "scanned PDF" in report["body"] and "<script>" not in report["body"]
    assert not any(n["title"].startswith("Problem report") for n in other.get("/api/notifications").json()["items"])
    acts = [x["action"] for x in admin.get("/api/audit").json()["items"]]
    assert "support.report" in acts
    with db.system():
        detail = db.conn().execute("SELECT detail FROM audit_log WHERE action='support.report'").fetchone()["detail"]
    assert "scanned PDF" not in detail                                                      # never the text itself
