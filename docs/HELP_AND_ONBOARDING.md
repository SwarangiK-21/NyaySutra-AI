# Help Centre, guided tour and tooltips

Phase 1 of the UI/UX improvement blueprint prepared after the Amdocs review (November 2026).

## Phase 0 decisions

| Question | Decision |
|---|---|
| What did the reviewers mean by "RAGES"? | **RAGAS** (Retrieval-Augmented Generation Assessment), an *evaluation* library for RAG systems. It does not replace the agent; it is planned for Phase 2 as an offline evaluation layer (faithfulness, answer relevancy, context precision and recall) on a lawyer-checked question set, never on real client data. |
| Support channel | **In-app "Report a problem"** (Help Centre): the report becomes a notification for every active administrator of the reporter's own organisation. No external support address or service is involved. |
| Help content languages | **English, Hindi and Marathi** (Marathi added in Phase 2). |
| Frontend framework | Stay with the existing plain-JavaScript frontend (no React migration now). New features are small modules. |
| Agent framework | Keep the custom orchestrator (`nyaya/agent.py`). LangGraph remains an optional later pilot; CrewAI and LlamaIndex are not planned. |

## What was built (Phase 1)

| Feature | Where | Notes |
|---|---|---|
| **Help Centre** at `#/help` | `web/js/help.js`, content in `web/help/en.json` and `web/help/hi.json` | Getting-started guides, FAQs and troubleshooting; instant search in the browser (no AI call); deep link to one article with `#/help?a=<id>`; public, so it also helps people who cannot sign in. Linked from the side rail ("?" icon), the profile menu and Ctrl+K. |
| **Report a problem** | Help Centre form → `POST /api/support` | Signed-in users only; 5 reports per hour per IP; topic + message (5–2000 characters). Notifies the organisation's administrators; the audit log records that a report was made, never its text. |
| **Guided tour** | `web/js/tour.js` | Spotlight with a pulsing outline, "Step n of N", **Previous / Next / Skip / Finish**, keyboard ← → Esc, focus kept in the tour card, screen-reader friendly. Steps the user has no permission for are left out. Starts automatically once for a signed-in user who has not finished or skipped it, resumes where it stopped, and restarts from "Take the tour again" (Help Centre, profile menu). |
| **Saved tour progress** | user preferences `tour_status`, `tour_step`, `tour_version` (`nyaya/server.py` `PREF_KEYS`) | Follows the user across devices; browser storage is the fallback. Raising `TOUR_VERSION` in `tour.js` shows the tour again to everyone after a big change. |
| **Accessible tooltips** | `web/js/ui.js` | Any `data-tip="…"` (and every existing `title="…"`, upgraded automatically) shows on hover **and** keyboard focus, closes with Esc, and is announced through `aria-describedby`. |
| **Actionable errors** | `web/js/core.js` (`helpFor`, `helpLink`) | Known error messages (AI credit, daily limit, rate limit, upload refused, quarantined, no permission, signed out) get a "What can I do?" link to the matching troubleshooting article, in toasts and in the research view. |
| **Phone-width sign-in check** | `web/app.css` | The earlier report of a cut-off sign-in page did not reproduce under real phone emulation (375 and 402 px: no overflow). The sign-in grid now uses `minmax(0, 1fr)` columns and wrapping tabs as a safeguard. |

## What was built (Phase 2)

| Feature | Where | Notes |
|---|---|---|
| **Quick-create "+"** | side rail, `web/index.html` (`#quickMenu`) | New case, upload & summarise, new calendar entry, draft, legal notice. Each item shows only with the matching permission. `#/cases?new=1` and `#/calendar?new=1` open the form directly. |
| **Contextual "?" help** | `contextHelp()` in `web/app.js` (`PAGE_HELP` map) | A small "?" after the page heading opens the Help Centre article for that page (cases, upload, documents, calendar, trash, drafting, account, library). |
| **Consistent pop-ups** | `confirmDialog` (`web/js/core.js`) | The remaining native `confirm()` boxes (delete document, delete case, delete conversation, clear searches, delete calendar entry) now use the app's own accessible dialog. |
| **Citation hover preview** | `citePreview()` in `web/app.js` | Hovering or focusing a citation like **[2]** shows the source's title and a short excerpt before opening it. |
| **Answer feedback 👍 / 👎** | `web/app.js`, `nyaya/server.py`, Administration → Answer quality | See `docs/EVALUATION.md`. |
| **RAGAS evaluation** | `eval/` | Offline scoring of a synthetic question set; see `docs/EVALUATION.md`. |
| **Marathi interface** | `web/i18n/mr.json` (all strings), `web/help/mr.json` (all articles); Marathi enabled in the language switch | Machine-assisted translation, checked for placeholders, line breaks and Markdown. **A review by a native Marathi speaker with legal vocabulary is still recommended** before a production launch. |
| **WCAG 2.2 AA fixes** | `web/app.css`, `web/js/awareness.js` | Placeholder (`[●]`) contrast, heading order on the awareness page, minimum 24×24 px targets (Success Criterion 2.5.8) for FAQ rows, text-size and language buttons. |

## Maintaining it

- **Help articles:** edit `web/help/en.json`, `web/help/hi.json` and `web/help/mr.json`. Keep the same article `id`s in all three files; the ids are used by deep links and by the error-to-article map in `core.js`. Answers are Markdown.
- **Tour steps:** `STEPS` in `web/js/tour.js` (selector, optional page and permission) and the `tour.<id>_title` / `tour.<id>_body` strings in `web/i18n/*.json`. Prefer stable element ids as selectors.
- **Interface strings:** every key in `web/i18n/en.json` must exist in `hi.json` and `mr.json` with the same `{placeholders}`; `tests/test_help.py` checks this.
- **Tests:** `tests/test_help.py` (tour preferences, problem reports, dictionary and help-article consistency), `tests/test_feedback.py` (answer feedback).
