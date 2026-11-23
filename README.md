<h1 align="center">⚖️ NyaySutra AI</h1>

<p align="center"><b>A secure, explainable legal-research assistant for Indian advocates — agentic RAG over official bare acts and your own case files, where every answer is cited and every citation is checked.</b></p>

<p align="center">
  <a href="https://github.com/SwarangiK-21/NyaySutra-AI/actions/workflows/ci.yml"><img src="https://github.com/SwarangiK-21/NyaySutra-AI/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Supabase-Postgres%20%2B%20RLS-3ECF8E?style=flat-square&logo=supabase&logoColor=white" alt="Supabase">
  <img src="https://img.shields.io/badge/RAG-BM25%20%2B%20dense%20%2B%20rerank-6A5ACD?style=flat-square" alt="Hybrid RAG">
  <img src="https://img.shields.io/badge/LLM-OpenAI%20gpt--6--luna-000000?style=flat-square&logo=openai&logoColor=white" alt="OpenAI gpt-6-luna">
  <img src="https://img.shields.io/badge/OCR-RapidOCR%20(ONNX)-FF6F00?style=flat-square" alt="OCR">
  <img src="https://img.shields.io/badge/tests-pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white" alt="pytest">
  <img src="https://img.shields.io/badge/status-working%20prototype-orange?style=flat-square" alt="Status">
</p>

<p align="center">
  <img src="docs/project_documentation/screenshots/04_research_answer.jpg" alt="NyaySutra research answer with numbered citations" width="900">
</p>

> **Group project.** Built by **Swarangi Kothawade** ([@SwarangiK-21](https://github.com/SwarangiK-21)), **Suraj Madane** ([@SurajM80](https://github.com/SurajM80)), **Abhishek Kanade** and **Ayush Bankar**. See [Team](#-team).
>
> *AI-generated research aid, not legal advice. Verify every citation against the primary source.*

---

## 📌 Problem statement

Indian legal research is slow and error-prone. Laws are long and frequently amended (criminal law moved from IPC/CrPC/Evidence Act to BNS/BNSS/BSA on 1 July 2024), every State has its own Acts, judgments run to many pages, and one matter can include scanned papers in English, Hindi and Marathi. General-purpose chatbots answer from memory and can **invent section numbers or case names** — for legal work, an invented citation is worse than no answer.

## 🎯 Objectives

1. Keep each matter and its documents in one secure workspace with per-case access control.
2. Answer **only from retrieved, numbered sources** (the lawyer's files + official bare acts) and abstain when the sources don't cover the question.
3. **Audit every citation automatically** against the source text and the Supreme Court judgment register.
4. Help with the daily workflow: drafting, limitation periods, hearings calendar, and legal updates.

---

## ✨ Key features

| Area | What it does |
|---|---|
| 🔎 **Legal research** | Streaming answers with `[n]` citations and an automatic citation audit, in English or Hindi; voice input (hi-IN / mr-IN / en-IN); focus on a single case document |
| 📁 **Case files** | Civil / Criminal / Family / Revenue / Consumer / Writ matters with CNR, FIR, court and jurisdiction fields; drafts for incomplete cases |
| 📄 **Documents** | 21 file types — PDF (incl. scanned, via built-in OCR), Word, Excel, CSV, PowerPoint, OpenDocument, RTF, text, images; language + script detection; translation and structured summaries linked to page numbers |
| 📚 **Law library** | 31 indexed bare acts (Constitution, BNS, BNSS, BSA, IPC, CPC, MLRC, Motor Vehicles Act…) with instant section lookup; India Code catalogue for all States/UTs with one-click import |
| ✍️ **Drafting studio** | 22 original templates × courts/forums; facts carry provenance, unknown facts stay as placeholders instead of guesses; review, versions, Word/PDF export (Hindi/Marathi shaped correctly) |
| 🧮 **Tools** | 24 deterministic limitation periods, applicable-provision suggestions (with IPC→BNS temporal checks), hearings calendar with server-side reminders |
| 🗑️ **Trash** | Deleted cases, documents, drafts and calendar entries go to a Trash for 30 days: hidden at once from lists, search and AI answers, restorable exactly as they were, then purged automatically (administrators can delete for good sooner) |
| 🔐 **Security** | Supabase Auth with e-mail verification + TOTP two-step, server-side sessions, roles and per-case membership, Postgres row-level security, invite-only sign-up, CSRF / Host / Origin checks and security headers, request-size limits, upload sandboxing, AI guardrails (English, Hindi, Marathi, base64 injection), per-person daily AI quota, append-only audit log |
| 🔒 **Database lock** | Data can only be changed through the app: edits made directly in the Supabase dashboard or SQL editor are refused, and anything that gets through is recorded in a tamper-proof change log |
| 🫀 **Keep-alive** | A scheduled GitHub Actions job pings the database every 3 days so the free Supabase project is never paused for inactivity, even when the app is off |
| 🌐 **Languages** | English / हिंदी interface; Marathi dictionary started |

---

## 🛠️ Technology stack

| Layer | Tools |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn, Server-Sent Events |
| Frontend | Vanilla JavaScript, HTML/CSS (government-portal theme), JSON i18n |
| Retrieval | Exact section lookup + BM25 + dense embeddings (fastembed, ONNX) → reciprocal rank fusion → cross-encoder rerank |
| LLM | OpenAI `gpt-6-luna` (answers, planning and verification; `LLM_PROVIDER=openai`). Alternative: `gpt-oss:120b` / `gpt-oss:20b` via Ollama Cloud or a local Ollama server (`LLM_PROVIDER=ollama`) |
| Data | Supabase Postgres + private Storage (Mumbai region) with row-level security; SQLite + FTS5 for fully offline use |
| Documents | PDFium (`pypdfium2`), RapidOCR, python-docx, openpyxl, python-pptx, fpdf2 + HarfBuzz |
| Quality | pytest (offline suite with fake LLM, fake OpenAI API, fake Supabase Auth and mocked feeds); GitHub Actions CI on every push: tests, Docker image build and health check on x86 and ARM, Snyk dependency, code and container scans |
| Deployment | Docker image (built and health-checked in CI), docker-compose and Caddy (HTTPS, size limits); step-by-step guide for an Oracle Cloud Always Free server — see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) and [docs/DEPLOY_ORACLE.md](docs/DEPLOY_ORACLE.md). Not hosted yet |

---

## 🏗️ Architecture

<p align="center">
  <img src="docs/project_documentation/diagrams/architecture.svg" alt="NyaySutra system architecture" width="900">
</p>

### RAG pipeline

<p align="center">
  <img src="docs/project_documentation/diagrams/rag_pipeline.svg" alt="RAG pipeline" width="900">
</p>

### Research agent

<p align="center">
  <img src="docs/project_documentation/diagrams/agent_flow.svg" alt="Research agent: one planner with allow-listed tools" width="800">
</p>

```
web/ (vanilla JS) ──SSE──► nyaya/server.py (FastAPI, security middleware)
                                 │
                                 ▼
                           nyaya/agent.py   plan → route
     ┌──────────────┬───────────────┬─────────┴───────┬──────────────────┐
  research       drafting      analyze_document   calculation        chitchat
     │              │               │                 │
 retrieval.py   template +      whole doc /       tools.py (Python
 exact + BM25 + retrieval       map-reduce        date arithmetic)
 dense + act-focus → RRF → cross-encoder rerank → weak? rewrite → abstain
     │
 llm.py (OpenAI gpt-6-luna: plan, answer, verify; Ollama optional) → stream → citation audit
     │
 db.py  Supabase Postgres + RLS (or SQLite offline) · authz.py · accounts.py + sessions.py · guardrails.py · trash.py
 ingest.py  parsing.py (PDFium) → chunking.py (section / paragraph / clause aware) → embeddings.py (fastembed ONNX)
```

**Chunking strategy.** Bare acts are split one chunk per Section / Article / Order-Rule with act, chapter and title in a context header (lookup keys such as `S138`, `A21`, `O39R1` enable exact retrieval). Judgments are grouped into ~1.1k-character chunks labelled by paragraph range; contracts and pleadings by numbered clause; everything else by sentence-aware windows with overlap.

**Design choices.** SQLite + FTS5 + NumPy for offline use (one file, ACID, BM25 built in, exact vector search over tens of thousands of chunks); fastembed (ONNX) instead of torch for a much smaller install and private embeddings; a cross-encoder reranker to gate weak evidence before the model answers.

More: [database design](docs/project_documentation/diagrams/database.svg) · [user journey](docs/project_documentation/diagrams/user_journey.svg) · [full project documentation](docs/project_documentation/NyaySutra_Project_Documentation.md)

---

## 🖼️ Screenshots

All screenshots are from the running application with synthetic data.

| Dashboard | Case documents |
|:---:|:---:|
| ![Dashboard](docs/project_documentation/screenshots/02_dashboard.jpg) | ![Case documents](docs/project_documentation/screenshots/03_case_documents.jpg) |
| **Citation audit** | **Drafting studio** |
| ![Citation audit](docs/project_documentation/screenshots/05_research_citation_audit.jpg) | ![Drafting studio](docs/project_documentation/screenshots/09_drafting_studio.jpg) |
| **India Code catalogue** | **Calendar** |
| ![India Code catalogue](docs/project_documentation/screenshots/08_india_code_catalogue.jpg) | ![Calendar](docs/project_documentation/screenshots/07_calendar.jpg) |

---

## 🚀 Installation and running

**Prerequisites:** Python 3.12, an [OpenAI API key](https://platform.openai.com/api-keys) with credit and a monthly budget (or, alternatively, an Ollama Cloud key or a local Ollama server). Supabase is optional — without it the app runs in local single-user mode on SQLite.

```powershell
git clone https://github.com/SwarangiK-21/NyaySutra-AI.git
cd NyaySutra-AI

# one-time: create the environment and install dependencies
py -3.12 -m venv "$env:USERPROFILE\.nyaysutra\venv"
& "$env:USERPROFILE\.nyaysutra\venv\Scripts\python.exe" -m pip install -r requirements-dev.txt   # app + test tools

# configure
Copy-Item .env.example .env      # then set LLM_PROVIDER=openai and OPENAI_API_KEY (and Supabase values if you use it)

# one-time: download official bare acts and build the law-library index (~25 min on a laptop CPU)
& "$env:USERPROFILE\.nyaysutra\venv\Scripts\python.exe" scripts\fetch_bare_acts.py
& "$env:USERPROFILE\.nyaysutra\venv\Scripts\python.exe" -m nyaya.ingest library

# run (opens http://127.0.0.1:8000)
& "$env:USERPROFILE\.nyaysutra\venv\Scripts\python.exe" run.py
```

On Windows you can also double-click **`start.bat`** after the one-time setup. On macOS/Linux use `python3.12 -m venv ~/.nyaysutra/venv` and `~/.nyaysutra/venv/bin/python`.

**Accounts (Supabase mode).** Set `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`, create the first administrator, then sign in and enable two-step verification:

```powershell
& "$env:USERPROFILE\.nyaysutra\venv\Scripts\python.exe" scripts\bootstrap_admin.py --email you@example.org
```

Supabase setup and migrations: [docs/SUPABASE_MIGRATION.md](docs/SUPABASE_MIGRATION.md) (the app checks the schema version at start-up; the current one is 8) · roles and dashboard settings: [docs/SECURITY.md](docs/SECURITY.md).

**Language model.** `LLM_PROVIDER=openai` with `LLM_MODEL=gpt-6-luna` (about ₹0.17 per research question at standard pricing; set a monthly budget in the OpenAI dashboard). `LLM_PROVIDER=ollama` switches back to Ollama Cloud or a local Ollama server. Personal identifiers (Aadhaar, PAN, phone, account numbers…) are masked before any text leaves the server. Web search uses Ollama's search API and is off by default with OpenAI.

**Keep-alive.** For the scheduled Supabase ping, add the repository secrets `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` (never the secret key); the workflow is `.github/workflows/supabase-keepalive.yml`.

**OCR.** Built in via RapidOCR (ONNX Runtime, no admin rights). Its English and Hindi/Marathi models (~40 MB) download on first use, or ahead of time with `python -m nyaya.ocr download`. Low-confidence words are shown as `[?word]` — text is never guessed. Tesseract is used instead if installed (`OCR_ENGINE=auto|rapidocr|tesseract|off`).

### Tests

```powershell
& "$env:USERPROFILE\.nyaysutra\venv\Scripts\python.exe" -m pytest
```

The offline suite (270 tests) uses synthetic records, a fake LLM, a fake OpenAI API, a fake Supabase Auth server (`tests/fake_auth.py`) and `httpx.MockTransport` for feeds, so it tests plumbing and safety logic — **not answer quality**. It costs nothing to run and never calls a real model. Opt-in live tests against a real Supabase project: set `NYAYA_LIVE_SUPABASE=1`.

---

## 📂 Project structure

```
NyaySutra-AI/
├── nyaya/                   # Backend package
│   ├── server.py            # FastAPI app, routes, security middleware
│   ├── agent.py             # Planner + router over allow-listed tools
│   ├── retrieval.py         # Exact + BM25 + dense retrieval, RRF, rerank, abstain
│   ├── citations.py         # Deterministic citation audit
│   ├── guardrails.py        # Request screening, injection flags, output secret filter
│   ├── ingest.py, parsing.py, chunking.py, ocr.py, embeddings.py
│   ├── drafting.py, provisions.py, judgments.py, indiacode.py
│   ├── llm.py               # OpenAI / Ollama client: streaming, retries, circuit breaker, PII masking
│   ├── trash.py             # Trash: move, restore, purge after 30 days
│   ├── accounts.py, sessions.py, authz.py, supabase_auth.py, privacy.py, retention.py
│   └── db.py, jobs.py, integrations.py, ...
├── web/                     # Vanilla JS frontend + i18n (en / hi / mr)
├── data/
│   ├── library/             # Official bare acts (with manifest + checksums), sample judgments, draft templates
│   └── cases.json, samples/ # Synthetic demo matters and documents
├── supabase/migrations/     # Postgres schema, RLS, storage, retention, edit lock, keep-alive, Trash
├── scripts/                 # Bare-act fetcher, India Code / SC catalogue import, admin bootstrap
├── tests/                   # Offline pytest suite (security, reliability, formats, grounding, ...)
├── docs/                    # Security, reliability, deployment, retention, project documentation, diagrams
├── deploy/                  # docker-compose + Caddy; oracle/setup-server.sh
├── .github/workflows/       # CI (tests, Docker x86 + ARM, Snyk) and the Supabase keep-alive
├── Dockerfile
└── run.py / start.bat
```

---

## 📊 Results

Measured on the project's own benchmark (files in [`docs/competitive_analysis/eval/`](docs/competitive_analysis/eval/)):

| Measure | Before | After | Source |
|---|---|---|---|
| Answers whose citations passed the audit (42 benchmark answers) | 17 / 42 (40%) | **31 / 42 (74%)** | `grounding_baseline.json` → `grounding_round4.json` |
| Feature-level evaluation checks | — | 31 / 31 passed | `results.json` (2026-10-28) |

Automated tests (November 2026): **270 offline tests pass** on every push in CI, together with the Docker image build and health check on x86 and ARM and Snyk scans. A STRIDE threat model and Snyk audit (November 2026) found 18 issues; all are fixed, accepted, or left to an owner decision (the full report stays outside the repository because it contains test evidence; the earlier risk register is [docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md)). These numbers describe this prototype's benchmark, not a lawyer-reviewed accuracy study.

## 💼 Use cases

- A junior advocate researching which BNSS section governs regular bail, with the exact text one click away.
- Summarising a bundle of scanned Marathi revenue papers into parties, dates, claims and deadlines.
- Drafting a Section 138 NI Act demand notice where every unknown fact is left as a visible placeholder.

## ⚠️ Limitations

- **Working prototype, not a production service.** It currently runs on one machine; the Docker image is built and tested in CI but not hosted yet. The security audit was done in-house (STRIDE + Snyk); no independent review or load test yet.
- **Coverage is curated:** 31 acts (29 central, 1 Maharashtra, 1 Karnataka) and 3 sample judgments — not a licensed case-law database. Awareness content covers central law and Maharashtra only.
- eCourts, Supreme Court, High Court and police portals are CAPTCHA-protected with no API, so case status is **manual import only**; CAPTCHAs, logins and rate limits are never bypassed.
- The citation audit reduces, but cannot eliminate, model errors (it does catch slips such as naming the wrong Sanhita). `gpt-6-luna` is a small, low-cost model; no lawyer-reviewed accuracy measurement exists yet.
- Questions, passages and (after consent) document text are sent to the AI provider (OpenAI) with identity numbers masked; names and facts are sent. OpenAI's API terms say this data is not used for training and is kept up to 30 days. For the most sensitive matters use a local Ollama server.
- Web search is off with the OpenAI provider, so questions outside the law library and case files get "not found" rather than a web answer.
- OCR runs on the CPU (roughly 5–20 s per scanned page). E-mail reminders are built but SMTP is not configured; virus scanning (ClamAV) is supported but not installed.
- Remaining security risks are tracked in [docs/SECURITY.md](docs/SECURITY.md) and [docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md).

## 🔭 Future enhancements

- Hosted deployment with HTTPS, backups and monitoring (Oracle Cloud guide ready: [docs/DEPLOY_ORACLE.md](docs/DEPLOY_ORACLE.md)).
- A lawyer-reviewed answer-quality evaluation and a load test.
- Wider State-law coverage and a licensed judgments source.
- Complete Marathi interface.
- A better layout of the sign-in page on narrow phone screens.

---

## 👥 Team

NyaySutra AI is a group project by four team members:

| Team member | GitHub |
|---|---|
| **Swarangi Kothawade** | [@SwarangiK-21](https://github.com/SwarangiK-21) |
| **Suraj Madane** | [@SurajM80](https://github.com/SurajM80) |
| **Abhishek Kanade** | — |
| **Ayush Bankar** | — |

### Code contributions (from the commit history)

| Contributor | Contributions |
|---|---|
| **Suraj Madane** ([@SurajM80](https://github.com/SurajM80)) | Original Streamlit + LangGraph prototype; rebuild as a lean agentic RAG app with the government-theme UI and official law library; project rename |
| **Swarangi Kothawade** ([@SwarangiK-21](https://github.com/SwarangiK-21)) | Case search, sync, multilingual documents, drafting studio and i18n; migration to Supabase (Postgres + private Storage) with row-level security; accounts, roles, case access and AI guardrails; durable job queue and LLM resilience; OCR and new upload formats; Supreme Court judgment catalogue and citation checking; grounding improvements (40% → 74%); search speed-up, data retention, privacy page and deployment setup; UI redesign; STRIDE + Snyk security audit and fixes; database edit lock and change log; CI with Docker (x86 + ARM) and Snyk scans; Oracle Cloud deployment guide; Supabase keep-alive; Trash (recycle bin); switch to OpenAI `gpt-6-luna`; project documentation |

Contributions are welcome — please open an issue describing the change first. Never commit `.env` files or real client documents.

## 📜 Data sources

- **Bare acts:** India Code (indiacode.gov.in), Legislative Department, Ministry of Law & Justice. IPC (repealed 1 July 2024, kept for pending matters): eCourts copy of the India Code text. Provenance and checksums: `data/library/bare_acts/manifest.json`.
- **Sample judgments:** Indian Kanoon.
- **Draft templates:** original model drafts written for this project — verify against current law and local practice.
- **Demo matters** in `data/cases.json` are fictional.
