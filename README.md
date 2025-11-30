CrediSynth QAA — FastAPI Service

Quick Start
- Create and activate a virtual environment.
- Install dependencies from `requirements.txt`.
- Run the API with Uvicorn.

Commands
```
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
set MOCK_MODE=true
uvicorn app.main:app --host 0.0.0.0 --port 5000 --reload
```

API
- `GET /health` — basic health check
- `POST /v1/analyze` — accept QSE JSON (see `sample_request.json`) and return qualitative synthesis

Notes
- By default `MOCK_MODE=true` returns a heuristic synthesis without calling the downstream AI.
- To use the AI integration, set `MOCK_MODE=false` and configure `GEMINI_API_KEY` and optional `GEMINI_MODEL`.

Docker
- Build: `docker build -t credisynth-qaa:local .`
- Run: `docker run --rm -p 5000:5000 --env-file .env.example credisynth-qaa:local`
- cURL: `curl -sS -X POST http://127.0.0.1:5000/v1/analyze -H "Content-Type: application/json" --data @sample_request.json | jq`

Observability & Auditing
- Metrics: Prometheus at `GET /metrics` (enabled automatically).
- Auditing: Set `DATABASE_URL` (e.g., `postgresql+asyncpg://user:pass@host:5432/db`) to record requests, results, and errors.
- Correlation ID: Provide `X-Correlation-ID` header to trace through logs and audit rows; generated if absent.
 - Auto-create DB: If the target database does not exist, the service will attempt to create it (requires privileges) and then create the audit tables.

Management Script
- Local build/start: `powershell -ExecutionPolicy Bypass -File .\scripts\manage.ps1 -Mode local -Action start`
- Local status/logs: `powershell -File .\scripts\manage.ps1 -Mode local -Action status` or `-Action logs`
- Local stop: `powershell -File .\scripts\manage.ps1 -Mode local -Action stop`
- Docker build/start: `powershell -ExecutionPolicy Bypass -File .\scripts\manage.ps1 -Mode docker -Action build` then `-Action start`
- Docker status/logs: `powershell -File .\scripts\manage.ps1 -Mode docker -Action status` or `-Action logs`
- Test API (either mode): `powershell -File .\scripts\manage.ps1 -Action test`

macOS/Linux (bash)
- Local build/start: `bash ./scripts/manage.sh --mode local --action start`
- Local status/logs: `bash ./scripts/manage.sh --mode local --action status` or `--action logs`
- Local stop: `bash ./scripts/manage.sh --mode local --action stop`
- Docker build/start: `bash ./scripts/manage.sh --mode docker --action build` then `--action start`
- Docker status/logs: `bash ./scripts/manage.sh --mode docker --action status` or `--action logs`
- Test API (either mode): `bash ./scripts/manage.sh --action test`

Port selection
- The manage script auto-selects a free port in `5000–5099` if `5000` is occupied.
- The chosen port is recorded at `logs/.local_api.port` for convenience.
- Docker runs map the selected host port to container `5000`.

Example
```
PORT=$(cat logs/.local_api.port)
curl -X POST http://localhost:${PORT}/v1/analyze \
  -H "Content-Type: application/json" \
  --data-binary @t:/CrediSynth/sample_request.json
```