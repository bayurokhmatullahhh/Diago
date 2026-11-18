# Digital Operator

Digital Operator is a local AI-agent workspace for tasks, coding assistance,
and defensive project checks. The current preview brings those capabilities
together around one agent entry point, with a FastAPI backend and React web app.

## Current MVP

- One Agent workspace with task, coding, and local Security tools in a shared navigation shell.
- Create, edit, complete, filter, and delete personal tasks.
- Add optional notes, a due date, and a separate reminder time.
- Review active, overdue, and completed task counts.
- Persist due reminders in an in-app notification inbox.
- Optionally receive browser notifications when the web app is open and permission is granted.
- Generate task drafts from natural-language instructions using configurable AI providers.
- Review/edit the proposed task; save only after explicit confirmation.
- Chat with the configured provider using recent conversation context; it can propose a todo, public-web research, or a local security scan, and waits for user approval before any action runs.
- Run an explicit public-web research query through Gemini Google Search grounding and show source links; the query is sent to Google/Gemini.
- Propose a change to one eligible workspace source file, review its diff, then explicitly apply or reject it.
- Run the fixed backend test command only after a separate confirmation.
- Run a read-only, local pattern-based security check without executing project code or sending source to an AI provider.
- Run a manually approved, passive HTTPS/TLS and security-header check against an explicitly allowlisted domain and URL path.
- Run a manually approved dependency advisory lookup for npm and PyPI packages.
- Persist tasks in SQLite by default.

The current app version is `0.3.0` (local preview). The release roadmap and
planned capability gates are documented in [docs/ROADMAP.md](./docs/ROADMAP.md).
Chat can propose a local read-only project security scan or public-web research.
The user sees the proposed action and must approve it before the UI calls the
existing tool endpoint; research queries are shown before they are sent to
Google/Gemini. Neither tool is executed directly by the model. Web research
returns source links and does not send project files, sign in, or interact with
websites. Coding changes remain reviewable proposals in the Coding tool; chat
does not apply code changes.

`due_at` is the task deadline; `reminder_at` is when the user wants a reminder.
The reminder worker writes delivered reminders to the database, so they remain in
the inbox across restarts. Browser notifications still require permission and an
open app tab; they are not push notifications and are not guaranteed while the
browser is closed or suspended.

## Stack

| Area | Technology |
|---|---|
| Backend API | Python, FastAPI, Pydantic |
| Database | SQLAlchemy, SQLite by default |
| Schema migrations | Alembic |
| Frontend | React, Vite |
| Tests | pytest, FastAPI TestClient |

## Setup

### Backend (Windows / PowerShell)

```powershell
.\scripts\setup.ps1
```

Or manually:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

### Frontend

Install Node.js, then:

```powershell
Set-Location frontend
npm install
```

### Database migration

Apply migrations from the project root after setup and whenever a migration is
added:

```powershell
.\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head
```

## Run locally

Run the backend from the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --app-dir backend --port 8000
```

Run the web app in a second terminal:

```powershell
Set-Location frontend
npm run dev
```

Run the reminder worker in a third terminal from the project root:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) "backend")
.\.venv\Scripts\python.exe -m app.scheduler.worker
```

The worker checks for due reminders every 15 seconds and persists each delivery
once. Keep this worker process running to process new reminders. Reminders that
became due while it was stopped are delivered after it restarts. For this local
MVP, run exactly one reminder worker against the SQLite database.

- Web app: http://localhost:5173
- API health: http://localhost:8000/health
- API docs: http://localhost:8000/docs

The frontend uses `http://localhost:8000` by default. Set `VITE_API_BASE_URL` in a frontend `.env` file to point it at another API origin.

## AI task planner

The web app can send a natural-language instruction to `POST /api/assistant/drafts`.
The backend tries the configured default provider first, then the configured
fallback order. Supported adapters are OpenAI, Google Gemini, Anthropic, and
OpenAI-compatible APIs such as local Ollama. Only configured providers are tried.

Copy the AI settings from `.env.example` into the project-root `.env` and add
provider API keys there. The keys are read by the backend and are never returned
by the provider-status API or sent to the browser. Choose model names that are
available to the account/provider. For a local OpenAI-compatible provider, set
its model and base URL; an API key is optional. Restart the backend after
changing `.env`.

The AI endpoint only returns a proposed draft. It does not write to the database
or execute actions. The user can review/edit the draft in the web app, and a
separate explicit confirmation creates the todo. Ambiguous instructions are
returned as clarification questions. Each configured provider may receive the
instruction text, so do not include sensitive information unless comfortable
sending it to that provider.

## Assistant chat

The assistant chat supports multi-turn conversation in the current browser
session. Up to the last 16 messages (maximum 16,000 characters total) are sent
to the configured provider for each response; chat history is not persisted by
the backend. Chat may suggest a todo, public-web research, or a read-only local
security scan. Suggestions do not execute automatically: the user must approve
them in the UI, and public research displays its query before sending it to
Google/Gemini. Todo proposals are not saved until confirmed. The assistant has
no shell, arbitrary browser, or unrestricted tool access. Do not send sensitive
information in chat because prompts and recent history go to the configured AI
provider.

## Coding agent (local MVP)

The coding agent can propose a replacement for one eligible source file at a
time. It does not have shell, browser, or general-purpose tool access. The API
requires explicit consent before sending source to a configured AI provider.
Review the complete diff and explicitly approve or reject it; approval is
refused if the file changed after the proposal was created. API keys,
environment files, build/dependency folders, and files matching known
credential patterns are excluded. This is a best-effort filter, not a guarantee
that every secret will be detected, so inspect the selected source before
consenting to send it to an AI provider.

The only runnable command is the backend test suite (`python -m pytest -q`).
Each run requires a separate confirmation because tests execute project code.
The app has no authentication or multi-user isolation: keep it bound to the
local machine and do not expose it to a network or the public internet. This
feature is for reviewed changes and defensive work in this project, not for
automatically attacking other systems.

## Local defensive checks

The Security page scans eligible source/configuration files in this project for
common risk patterns, including hardcoded-secret-like values, disabled TLS
verification, dynamic code execution, wildcard CORS, and raw HTML injection
markers. Python files also receive AST checks for dynamic SQL construction,
unsafe deserialization, unsafe YAML loading, and subprocess calls using
`shell=True`. Multiline configuration patterns are supported. Results contain
file paths and line numbers, but do not include matched source or secret values.
Environment files, hidden directories, documentation for code-pattern checks,
databases, dependency/build directories, and lockfiles are excluded. The scan
is local, read-only, makes no network requests, and does not execute project
code or send files to an AI provider.

This is a best-effort heuristic, not a full security audit: it may miss issues
or flag harmless test/example code. A clean result does not prove that the
project is secure.

The separate website check is disabled until exact hostnames are configured in
`SECURITY_AUDIT_ALLOWED_HOSTS` in the backend `.env` file. It requires an
authorization checkbox and a confirmation dialog, then makes one HTTPS GET to
the URL path entered for that exact host. Query strings and fragments are not
sent, redirects are not followed, and response bodies are not included in the
report. It checks TLS validation and common security headers only. It does not
crawl, log in, send exploit payloads, brute-force, or access private data. A
site may still attach side effects to a GET endpoint, so use only known
read-only paths on domains you own or have explicit permission to assess. This
is not a full penetration test.

The dependency audit uses `npm audit` and `pip-audit` to compare lockfile and
requirements versions with published advisories. It requires a separate
confirmation because package names and versions are sent to npm and PyPI
advisory services; source code and secrets are not sent. It does not install
updates or exploit reported issues. Review advisory details and compatibility
before upgrading packages.

## API

- `GET /api/assistant/providers` — provider names, models, and configured status (never API keys)
- `POST /api/assistant/chat` — multi-turn response with an optional, uncommitted todo or approved-tool proposal
- `POST /api/assistant/drafts` — create a reviewable AI task draft; does not persist it
- `POST /api/agent/research` — explicit public web research through Gemini Google Search grounding with source citations
- `POST /api/agent/security-scan` — run local read-only pattern checks on project source/configuration
- `POST /api/agent/website-security-check` — check TLS and common headers on one explicitly allowlisted host after authorization confirmation
- `POST /api/agent/dependency-audit` — compare frontend/backend dependency versions against npm/PyPI advisories after explicit confirmation
- `GET /api/agent/files` — list eligible source files for a coding proposal
- `GET /api/agent/proposals` — list pending coding proposals
- `POST /api/agent/proposals` — create a one-file proposal for review
- `POST /api/agent/proposals/{id}/approve` — apply a reviewed proposal if the source is unchanged
- `POST /api/agent/proposals/{id}/reject` — reject a proposal without changing the source
- `POST /api/agent/commands/run` — run backend tests after explicit confirmation
- `GET /api/todos` — list tasks; accepts optional `status=pending|completed`
- `POST /api/todos` — create a task
- `PATCH /api/todos/{id}` — update task fields or status
- `DELETE /api/todos/{id}` — delete a task
- `GET /api/notifications` — list recent reminder notifications and unread count
- `PATCH /api/notifications/{id}/read` — mark a notification as read
- `PATCH /api/notifications/read-all` — mark all notifications as read

When providing `due_at` or `reminder_at` through the API, use an ISO-8601
datetime with a timezone, such as `2026-11-12T08:30:00+07:00`.

## Tests and build

From the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Build the frontend:

```powershell
Set-Location frontend
npm run build
```

## Security note

This MVP is intended for local, single-user development. It does not have authentication or multi-user data isolation. Do not expose it to the public internet or use it for sensitive data until those controls are implemented.

## Next direction

The task, reminder, and AI draft flow is the first usable slice, not the final
product. The next steps can improve real-provider validation and carefully
scoped integrations as separate capabilities.

See [docs/ROADMAP.md](./docs/ROADMAP.md) for the product vision, current
architecture, phased roadmap, terminology, and recommended next steps.
