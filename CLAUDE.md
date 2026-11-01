# Job Tracker

A personal job-application tracker. It reads the inbox over IMAP, finds "thanks for applying"
confirmation emails and creates an application for each one automatically. The user changes
statuses by hand (Applied → OA → Interview → Offer / Rejected / Ghosted / Withdrawn) in a web
dashboard. The goal: never type in an application after applying.

See `PLAN.md` for the issue list, what's done, and what's next.

## Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2, SQLite (Postgres later via `DATABASE_URL`)
- **Email:** stdlib `imaplib` with a Gmail App Password (no OAuth: avoids the 7-day refresh-token
  expiry Google applies to OAuth apps left in "Testing" mode)
- **Classification:** plain regex rules in `backend/app/parser.py`. No LLM yet (see PLAN backlog)
- **Frontend:** React + Vite + TypeScript in `frontend/`, plain CSS, no UI framework

## Layout

```
backend/
  app/
    config.py   settings from env / backend/.env
    db.py       engine, session, init_db (create_all; no migrations yet)
    models.py   Application, StatusEvent (history), EmailRecord (every email looked at), Meta
    parser.py   classify(email) -> confirmation | review | ignore, + company/role extraction
    mail.py     IMAP source: headers first, bodies only for prefilter candidates, BODY.PEEK
    sync.py     mailbox -> prefilter -> classify -> dedupe -> DB; per-email commits
    main.py     FastAPI routes under /api; serves frontend/dist at / if built
    cli.py      python -m app.cli sync | test-imap | seed-demo
  tests/        pytest; FakeMailbox in test_sync_api.py, realistic samples in test_parser.py
frontend/
  src/
    api.ts      typed fetch wrappers + types mirroring backend/app/schemas.py
    format.ts   date / "N days ago" helpers
    App.tsx     state, tabs, optimistic status changes, sync button
    components/ Header, StatsStrip, Board + AppCard (drag to change status), TableView
```

## Commands

```bash
cd backend
pip install -r requirements.txt
python -m pytest -q                  # all tests
python -m app.cli seed-demo          # fake data to try the UI
uvicorn app.main:app --reload        # API on :8000
python -m app.cli sync               # one sync run (cron calls this)

cd ../frontend
npm install
npm run dev                          # UI on :5173, proxies /api to :8000
npm run build                        # typecheck + build to dist/, served by FastAPI at /
npm run lint
```

## Workflow (same as the user's `insync` repo, keep it this way)

- **One GitHub issue per feature or fix**, small and specific.
- **Branch per issue, PR per branch, squash-merge** so `main` has one commit per PR.
- **PR / squash commit title = conventional commit in plain English:**
  `feat(parser): detect confirmation emails and pull out the company and role (#7)`
  Types: `feat`, `fix`, `docs`, `test`, `chore`, `refactor`. Scopes: `repo`, `db`, `parser`,
  `mail`, `sync`, `cli`, `api`, `web`, `readme`.
- **Body:** 1–3 sentences on *how*, then `Closes #N`.
- First commit `chore: initial commit`, then `chore(repo): scaffold ...`.
- Tests pass before every merge. A new parser case gets a test in `tests/test_parser.py`.
- Never commit `.env`, `*.db`, or real email content (sanitize samples: fake names/companies).

## Design decisions (don't undo without asking)

- **Email only creates entries; statuses are manual.** The user explicitly wants this. Rejection,
  OA, interview and offer emails are *ignored* by the parser on purpose (checked before
  confirmation phrases, since rejections also say "thank you for applying").
- **Three outcomes:** `confirmation` (auto-create), `review` (one-click accept in the UI, used when
  the company can't be found or is only guessed from a non-ATS sender), `ignore` (stored with a
  reason so missed emails can be rescued from a "skipped" list).
- **Idempotent sync:** `EmailRecord.message_id` is unique; re-running sync never duplicates.
- **Duplicates:** same normalized company + same role (or either role blank) within
  `DUPLICATE_WINDOW_DAYS` → linked as duplicate; fills in a missing role.
- **Deleting an application** marks its emails `dismissed` so a re-sync doesn't recreate it.
- **"Possibly ghosted"** is a computed flag (applied ≥ `GHOST_AFTER_DAYS`), never auto-applied.
- **Work laptop:** the user applies from a managed work laptop too. Email-based creation works
  regardless of device; no extension or software should be required on that machine.
