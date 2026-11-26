# Answer evaluation (RAGAS) and answer feedback

Two complementary ways to measure answer quality, added in Phase 2 of the UI/UX blueprint (November 2026).

| | Offline RAGAS evaluation | In-app answer feedback |
|---|---|---|
| What | An AI judge scores saved answers on a fixed **synthetic** question set | Lawyers rate real answers 👍 / 👎 with an optional reason |
| When | Run by a developer before or after a change (retrieval, prompts, model) | Continuously, while people use the app |
| Data | `eval/questions.json` only, never client data | Rating, reason and optional comment per answer, per person |
| Where the result is | `eval/runs/<timestamp>/ragas_report.md` | Administration → **Answer quality** |

## 1. RAGAS evaluation

[RAGAS](https://docs.ragas.io) (Retrieval-Augmented Generation Assessment) is an evaluation library. It does **not** change how the app answers: NyaySutra's own agent produces the answers and RAGAS only scores them.

### Metrics

| Metric | Question it answers | Needs a reference answer? |
|---|---|---|
| `faithfulness` | Are the answer's claims supported by the passages the model was given? | No |
| `answer_relevancy` | Does the answer address the question? | No |
| `llm_context_precision_without_reference` | Were the retrieved passages useful for this answer? | No |
| `context_recall` | Did retrieval find everything needed? | **Yes**, scored only when every question has a `reference` |

All scores are 0–1, higher is better. They come from an AI judge: treat them as **indicative trends**, not as a lawyer's review.

### Install (evaluation only)

The app, its tests and the Docker image do not need any of this. Use the app's virtual environment:

```
pip install --no-deps ragas==0.4.3
pip install -r requirements-eval.txt
```

`--no-deps` skips RAGAS's test-set generator dependency (scikit-network), which has no ready-made build for Python 3.14 on Windows and is not used for scoring. `langchain-community` is pinned below 0.4 because RAGAS 0.4.3 imports a module that 0.4 removed. On Windows, Smart App Control may briefly block a freshly installed DLL (for example pandas); running the command again usually works.

### Run

```
python eval/collect_answers.py --limit 3                        # step 1: answer the questions with the real agent
python eval/ragas_eval.py eval/runs/<timestamp>/answers.jsonl   # step 2: score them
```

- Step 1 runs `agent.run()` exactly as the app does, but stubs chat saving and the audit log, so **nothing is written to the database**. It records each answer and the passages the answer model received. Select questions by id (`R01 R05`) or with `--limit`.
- Step 2 uses the app's own LLM client as the judge (`nyaya/llm.py`: identity numbers masked, unsupported settings such as `temperature` dropped automatically) and the app's local embedding model. Default judge: `FAST_LLM_MODEL`; override with `--model`.
- Output: `answers.jsonl`, `ragas_scores.json` and `ragas_report.md` in the run folder. `eval/runs/` is git-ignored.

**Cost:** about ₹0.17 per answer on gpt-6-luna, plus roughly 10–15 judge calls per answer. Run small sets.

### Question set

`eval/questions.json` holds 12 synthetic general-law questions (statute lookup, old/new code mapping, procedure, constitutional, family, consumer, limitation, case law, and one in Hindi). Each has an optional `reference`: an expected answer **written or checked by a lawyer**. When every question has one, context recall is scored too. Never add client material.

### Validation run (26 November 2026)

| Metric | Mean |
|---|---|
| faithfulness | 0.867 |
| answer_relevancy | 0.844 |
| context precision (no reference) | 0.85 |

Two questions (R01 Section 138 NI Act, R02 punishment for murder under BNS); answer model and judge gpt-6-luna. Both answers also passed the app's own citation check. This run proves the pipeline works; it is too small to be a benchmark. A full 12-question run with lawyer-written references is the next step.

## 2. Answer feedback (👍 / 👎)

Under every research answer: **Was this answer helpful?** 👍 / 👎. After 👎 the person can pick a reason (wrong law or section, citation does not support it, incomplete, not what I asked, language or wording, something else) and add an optional comment (up to 500 characters, no client details).

- `PUT /api/chats/{chat_id}/messages/{message_id}/feedback` with `{rating: "up" | "down" | "none", reason, comment}`. Only the owner of the conversation can rate, only assistant messages, 60 requests per minute. `"none"` withdraws the rating; clicking the same thumb again does that.
- Stored in `answer_feedback` (one row per message and person; Supabase migration `20261126000014_answer_feedback.sql`, local SQLite migration 7, schema version 9) with row-level security: each person reads and changes only their own ratings.
- The audit log records `ai.feedback` with the rating and reason, **never the comment**.
- `GET /api/admin/feedback?days=30` (permission `audit.read`) returns counts for the administrator's own organisation: 👍, 👎, and 👎 by reason. Comments are not included. Shown in Administration → **Answer quality**.

Use the 👎 reasons to choose which questions to add to the RAGAS set: a cluster of "citation does not support it" points to the citation audit, "not what I asked" to query planning, "incomplete" to retrieval depth.

Tests: `tests/test_feedback.py`.
