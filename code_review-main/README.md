# Agentic Code Reviewer

Production-style repository review platform for uploaded GitHub ZIPs. It maps a repository, selects review targets, runs deterministic engineering checks, optionally uses DeepSeek or Gemini for synthesis, and returns a file-level review report with patch guidance.

## What it reviews

- Frontend/SvelteKit startup and accessibility issues
- FastAPI route and dependency problems
- Frontend/backend API contract drift
- Security risks such as hardcoded secrets, unsafe ZIP extraction, and broad CORS
- Database bottlenecks such as looped queries and SQLite concurrency gaps
- DevOps readiness, CI gaps, Docker/environment readiness
- Git workflow and PR checklist gaps
- MCP server tool naming, parameter, and secret-handling patterns

## Run backend

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --host 127.0.0.1 --port 8004
```

## Run frontend

```bash
cd apps/web
npm install --registry=https://registry.npmjs.org/
npm run dev -- --host 0.0.0.0
```

Create `apps/web/.env` if needed:

```env
VITE_API_BASE_URL=http://localhost:8004
```

## Optional LLM review

Set in `apps/api/.env`:

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_key
DEEPSEEK_MODEL=deepseek-chat
```

or:

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key
GEMINI_MODEL=gemini-1.5-flash
```

Offline deterministic review remains available with `LLM_PROVIDER=offline`.

## Routes

- `GET /api/v1/review/health`
- `POST /api/v1/review/upload`
- `GET /api/v1/review/files/{session_id}`
- `POST /api/v1/review/run`
- `GET /api/v1/review/sessions`
- `GET /api/v1/review/skills`
- `GET /api/v1/review/memory/{session_id}`
