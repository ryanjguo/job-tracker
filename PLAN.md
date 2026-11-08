# Plan

## Status

The backend (issues 1–8) is landed, one PR per issue (22 tests passing). Issues 9–10 (the dashboard)
and 11 (README) are landed.

## Issues

| # | Title (also the squash commit title) | Files | State |
|---|---|---|---|
| 1 | `chore(repo): scaffold backend and frontend` | `.gitignore`, `CLAUDE.md`, `PLAN.md`, `backend/requirements.txt`, `backend/.env.example`, `backend/app/__init__.py`, `backend/app/config.py`, `backend/app/db.py`, `frontend/` (Vite React-TS scaffold) | done |
| 2 | `feat(db): store applications, status history and processed emails` | `models.py` | done |
| 3 | `feat(parser): detect confirmation emails and pull out the company and role` | `parser.py`, `tests/test_parser.py` | done |
| 4 | `feat(mail): read the inbox over IMAP without marking anything read` | `mail.py` | done |
| 5 | `feat(sync): create applications from confirmations, skip duplicates, queue unsure ones` | `sync.py`, `tests/conftest.py`, sync tests | done |
| 6 | `feat(cli): add sync, test-imap and seed-demo commands` | `cli.py` | done |
| 7 | `feat(api): list, add, edit and change status of applications` | `main.py` (applications routes), `schemas.py` | done |
| 8 | `feat(api): add review queue, sync-now and stats endpoints` | `main.py` (rest), API tests | done |
| 9 | `feat(web): kanban board with drag to change status` | `frontend/` | done |
| 10 | `feat(web): review queue, skipped emails, and add/edit forms` | `frontend/` | done |
| 11 | `docs(readme): setup, architecture and design decisions` | `README.md` | done |
| 22 | `feat(cli): import applications from a spreadsheet CSV` | `importer.py`, `cli.py`, `tests/test_import.py` | done |
| 24 | `feat(db): add location, term, next action and follow-up date to applications` | `models.py`, `db.py`, API, `importer.py`, `frontend/` | done |
| 26 | `fix(parser): stop dropping confirmations that mention next steps` | `parser.py`, tests | done |
| 27 | `fix(parser): read the role from "Your application to Acme \| Role" subjects` | `parser.py`, tests | done |
| 28 | `feat(sync): sync automatically on a schedule while the server runs` | `scheduler.py`, `sync.py`, `main.py`, header | done |
| 29 | `feat(web): search and filter the board` | `frontend/` | done |
| 30 | `fix(web): open cards from the keyboard` | `frontend/` | done |
| 31 | `feat(sync): suggest status changes from rejection, OA and interview emails` | | needs a decision |
| 38 | `fix(parser): stop saving wrong roles and companies from common ATS wording` | `parser.py`, tests | done |
| 39 | `feat(cli): re-check skipped emails with the current parser rules` | `sync.py`, `mail.py`, `cli.py` | done |
| 40 | `fix(api): open Gmail links in the account that received the email` | `main.py` | done |
| 41 | `fix(api): only accept http(s) links for postings` | `urls.py`, schemas, importer, `frontend/` | done |
| 42 | `fix(api): refuse requests from other websites` | `main.py`, `config.py`, `api.ts` | done |
| 43 | `feat(api): export applications as CSV` | `exporter.py`, `main.py`, `cli.py`, table view | done |

Note for 7/8: `main.py` and `schemas.py` hold both; split by route group, or land both in 7 and
keep 8 for the remaining endpoints + tests. Each PR must pass tests on its own.

## API (already implemented)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/applications` | newest first; each has `days_since_applied`, `possibly_ghosted`, `email_url` (Gmail deep link), `events` |
| POST | `/api/applications` | manual add: `company` (required), `role`, `applied_date`, `job_url`, `notes`, `status` |
| PATCH | `/api/applications/{id}` | any field; a `status` change appends a StatusEvent |
| DELETE | `/api/applications/{id}` | linked emails become `dismissed` |
| GET | `/api/emails?outcome=review` | review queue; `outcome=ignored` = skipped emails |
| POST | `/api/emails/{id}/accept` | `{company, role, job_url}` → creates application |
| POST | `/api/emails/{id}/dismiss` | |
| POST | `/api/sync` | runs IMAP sync; 400 if not configured, 502 on login failure |
| GET | `/api/stats` | `by_status`, `response_rate`, `median_days_to_response`, `applied_last_7_days`, `possibly_ghosted`, `per_week` (12 weeks) |
| GET | `/api/meta` | `imap_configured`, `last_sync_at`, `review_count`, `statuses`, `ghost_after_days` |

## Frontend spec (issues 9–10)

- Vite + React + TypeScript, no UI framework needed; dev server proxies `/api` → `:8000`.
  `npm run build` → `frontend/dist`, which FastAPI serves at `/` (one process in production).
- **Header:** title, last-synced time, "Sync now" button (shows the summary or error), "+ Add".
- **Stats strip:** total, applied in last 7 days, response rate, median days to response,
  possibly-ghosted count.
- **Board (default view):** a column per status; cards show company, role, applied date /
  "N days ago", ATS badge, links (posting, email). Drag a card to another column = PATCH status.
  Possibly-ghosted cards get a subtle highlight + "Mark ghosted" button.
- **Table view:** sortable, search box, inline status dropdown.
- **Review tab** (badge with `review_count`): each item shows subject, sender, snippet, editable
  company/role prefilled from guesses, Accept / Dismiss, "Open email". Collapsible "Skipped emails"
  list (`outcome=ignored`) with the skip reason and an "Add as application" action.
- **Edit modal:** click a card → edit company, role, date, URL, notes, status; delete.

## Backlog (after v1)

- LLM fallback for the review queue only (Claude Haiku tool-use with a status enum).
- Enricher: find the posting URL via Greenhouse / Lever public job-board APIs.
- Posting watcher: flag saved postings that went offline (likely filled).
- Morning digest (Discord/Telegram/email): new entries, items to review, follow-ups due.
- Hosted Postgres (Supabase/Neon) + auth, so the dashboard works from any device.
- Optional one-click clipper (bookmarklet) to save full job descriptions.
