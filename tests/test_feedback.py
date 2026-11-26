"""Answer feedback (👍 / 👎 with a reason), offline with the suite's fake model: only the chat's owner can rate its
answers, ratings come back with the chat, and administrators see counts for their own organisation only."""
from __future__ import annotations

from nyaya import db
from test_security import chat, fake, person, signed_in  # noqa: F401


def _answer(c, question="Is the security deposit refundable?"):
    r, events = chat(c, message=question)
    assert r.status_code == 200
    chat_id = next(e["chat_id"] for e in events if e["type"] == "chat")
    mid = next(e["message_id"] for e in events if e["type"] == "done")
    return chat_id, mid


def test_rate_change_and_withdraw_feedback(fake):
    person(fake, "adv@example.com", "advocate")
    a = signed_in("adv@example.com")
    chat_id, mid = _answer(a)
    url = f"/api/chats/{chat_id}/messages/{mid}/feedback"
    assert a.put(url, json={"rating": "up"}).json()["rating"] == "up"
    msgs = a.get(f"/api/chats/{chat_id}").json()["messages"]
    assert next(m for m in msgs if m["id"] == mid)["feedback"] == {"rating": "up", "reason": ""}
    assert a.put(url, json={"rating": "down", "reason": "wrong_citation", "comment": "Cites s.138 of the wrong Act"}).status_code == 200
    msgs = a.get(f"/api/chats/{chat_id}").json()["messages"]
    assert next(m for m in msgs if m["id"] == mid)["feedback"] == {"rating": "down", "reason": "wrong_citation"}
    assert a.put(url, json={"rating": "none"}).status_code == 200
    assert next(m for m in a.get(f"/api/chats/{chat_id}").json()["messages"] if m["id"] == mid)["feedback"] is None
    # Validation and targets: a user's own question cannot be rated; unknown reasons and long comments are refused.
    user_msg = next(m for m in msgs if m["role"] == "user")["id"]
    assert a.put(f"/api/chats/{chat_id}/messages/{user_msg}/feedback", json={"rating": "up"}).status_code == 404
    assert a.put(url, json={"rating": "down", "reason": "boring"}).status_code == 422
    assert a.put(url, json={"rating": "down", "comment": "x" * 501}).status_code == 422
    with db.system():
        detail = db.conn().execute("SELECT detail FROM audit_log WHERE action='ai.feedback' ORDER BY id DESC LIMIT 1").fetchone()
    assert "wrong Act" not in (detail["detail"] if detail else "")                 # the comment is never audited


def test_others_cannot_rate_and_admin_summary_is_per_organisation(fake):
    with db.system(), db.tx() as c:
        c.execute("INSERT INTO organizations(id, name, created_at) VALUES('org_b', 'Other firm', ?)", (db.now(),))
    person(fake, "adv@example.com", "advocate")
    person(fake, "col@example.com", "advocate")
    person(fake, "admin@example.com", "admin")
    person(fake, "other-admin@example.com", "admin", org="org_b")
    a, col, admin, other = (signed_in(e) for e in ("adv@example.com", "col@example.com", "admin@example.com",
                                                    "other-admin@example.com"))
    chat_id, mid = _answer(a)
    assert col.put(f"/api/chats/{chat_id}/messages/{mid}/feedback", json={"rating": "down"}).status_code == 404
    a.put(f"/api/chats/{chat_id}/messages/{mid}/feedback", json={"rating": "down", "reason": "incomplete"})
    chat2, mid2 = _answer(col, "What is the limitation period for a money suit?")
    col.put(f"/api/chats/{chat2}/messages/{mid2}/feedback", json={"rating": "up"})

    s = admin.get("/api/admin/feedback").json()
    assert s["up"] == 1 and s["down"] == 1 and s["reasons"]["incomplete"] == 1
    assert other.get("/api/admin/feedback").json()["up"] == 0                     # another firm sees none of it
    assert a.get("/api/admin/feedback").status_code == 403                         # lawyers do not get the summary
