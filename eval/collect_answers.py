"""RAGAS step 1: run the evaluation questions through the real research agent and save what it answered and which
passages it was given. Nothing is written to the database (chat saving and audit are stubbed), and only the synthetic
questions in eval/questions.json are used — never client data.

    python eval/collect_answers.py              # all questions
    python eval/collect_answers.py --limit 3    # the first 3 (each answer costs about ₹0.17 on gpt-6-luna)
    python eval/collect_answers.py R01 R05      # selected ids

Writes eval/runs/<timestamp>/answers.jsonl, which eval/ragas_eval.py scores.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nyaya import agent, config, db  # noqa: E402
from nyaya.vectorindex import index  # noqa: E402

TOKEN_TYPES = {"token", "final"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ids", nargs="*", help="question ids to run (default: all)")
    ap.add_argument("--limit", type=int, default=0, help="run only the first N questions")
    ap.add_argument("--out", default="", help="output folder (default: eval/runs/<timestamp>)")
    args = ap.parse_args()

    data = json.loads((ROOT / "eval" / "questions.json").read_text("utf-8"))["questions"]
    if args.ids:
        data = [q for q in data if q["id"] in args.ids]
    if args.limit:
        data = data[: args.limit]
    if not data:
        print("No questions selected.")
        return 2

    # Same stubs as docs/competitive_analysis/eval/run_eval.py: no chats, messages or audit rows are written.
    agent.ensure_chat = lambda chat_id, case_id, first: "chat_eval"
    agent.save_message = lambda *a, **k: 0
    agent.history = lambda chat_id, limit=8: []
    db.audit = lambda *a, **k: None
    # Record the passages the answer model was given (the first context built for each question).
    captured: list[list[str]] = []
    real_context = agent._context

    def recording_context(hits):
        captured.append([f"{h.header}\n{h.text}" for h in hits])
        return real_context(hits)

    agent._context = recording_context
    db.init()
    index.load()

    out = Path(args.out) if args.out else ROOT / "eval" / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "answers.jsonl"
    print(f"Model: {config.LLM_MODEL} via {config.LLM_PROVIDER} · {len(data)} question(s) → {path}")
    with path.open("w", encoding="utf-8") as f:
        for q in data:
            captured.clear()
            t0 = time.time()
            answer, meta, error = [], {}, None
            for evt in agent.run(message=q["question"], lang=q.get("lang", "en"), jurisdiction="all"):
                if evt["type"] == "token":
                    answer.append(evt["text"])
                elif evt["type"] == "final":
                    answer = [evt["text"]]
                elif evt["type"] == "error":
                    error = evt["text"]
                elif evt["type"] == "done":
                    meta = evt.get("meta") or {}
            row = {"id": q["id"], "category": q["category"], "lang": q.get("lang", "en"), "user_input": q["question"],
                   "response": "".join(answer).strip(), "retrieved_contexts": captured[0] if captured else [],
                   "reference": q.get("reference") or "", "intent": meta.get("intent"), "error": error,
                   "abstained": bool(meta.get("abstained")), "verified": (meta.get("verify") or {}).get("grounded"),
                   "seconds": round(time.time() - t0, 1), "model": config.LLM_MODEL}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            status = "error: " + error if error else f"{len(row['retrieved_contexts'])} passages"
            print(f"  {q['id']:4} {row['seconds']:5.1f}s  {status}")
    print(f"Done. Next: python eval/ragas_eval.py {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
