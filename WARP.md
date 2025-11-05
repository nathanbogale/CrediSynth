# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Commands

### Local Development (Windows PowerShell)
```powershell
# Setup virtual environment and install dependencies
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

# Run API in mock mode (no Gemini API calls)
$env:MOCK_MODE="true"
uvicorn app.main:app --host 0.0.0.0 --port 7000 --reload

# Run API with Gemini integration
$env:MOCK_MODE="false"
$env:GEMINI_API_KEY="your-key-here"
uvicorn app.main:app --host 0.0.0.0 --port 7000 --reload
```

### Local Development (macOS/Linux bash)
```bash
# Setup and run
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export MOCK_MODE=true
uvicorn app.main:app --host 0.0.0.0 --port 7000 --reload
```

### Management Scripts (Windows)
```powershell
# Local mode operations
powershell -ExecutionPolicy Bypass -File .\scripts\manage.ps1 -Mode local -Action start
powershell -File .\scripts\manage.ps1 -Mode local -Action status
powershell -File .\scripts\manage.ps1 -Mode local -Action logs
powershell -File .\scripts\manage.ps1 -Mode local -Action stop

# Docker operations
powershell -ExecutionPolicy Bypass -File .\scripts\manage.ps1 -Mode docker -Action build
powershell -File .\scripts\manage.ps1 -Mode docker -Action start
powershell -File .\scripts\manage.ps1 -Mode docker -Action status

# Test API
powershell -File .\scripts\manage.ps1 -Action test
```

### Management Scripts (macOS/Linux)
```bash
# Local mode
bash ./scripts/manage.sh --mode local --action start
bash ./scripts/manage.sh --mode local --action status
bash ./scripts/manage.sh --mode local --action stop

# Docker
bash ./scripts/manage.sh --mode docker --action build
bash ./scripts/manage.sh --mode docker --action start

# Test
bash ./scripts/manage.sh --action test
```

### Docker Commands
```bash
# Build
docker build -t credisynth-qaa:local .

# Run
docker run --rm -p 7000:7000 --env-file .env.example credisynth-qaa:local

# Test
curl -sS -X POST http://127.0.0.1:7000/v1/analyze \
  -H "Content-Type: application/json" \
  --data @sample_request.json | jq
```

### API Testing
```bash
# Health check
curl http://localhost:7000/health

# Analyze request (Windows)
curl -X POST http://localhost:4000/v1/analyze ^
  -H "Content-Type: application/json" ^
  --data-binary @sample_request.json

# Analyze request (Unix)
curl -X POST http://localhost:7000/v1/analyze \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: test-correlation-123" \
  --data-binary @sample_request.json

# Metrics
curl http://localhost:7000/metrics
```

## Architecture

### System Overview
CrediSynth QAA (Qualitative Analysis Agent) is a FastAPI microservice that synthesizes complex quantitative credit scoring outputs (QSE JSON) into concise, human-readable qualitative reports for loan officers and credit committees at the National Bank of Ethiopia.

**Core Flow:**
1. Upstream QSE (Quantitative Scoring Engine) generates comprehensive JSON with 164+ features, SHAP values, risk scenarios, and NBE compliance
2. QAA API receives QSE JSON via `POST /v1/analyze`
3. Service validates input with Pydantic models (extra fields ignored for forward compatibility)
4. Two execution modes:
   - **MOCK_MODE=true**: Heuristic fallback synthesis (no AI call) for dev/testing
   - **MOCK_MODE=false**: Gemini 1.5 Pro generates qualitative report via JSON Mode
5. Returns `QAAQualitativeReport` with executive summary, ability/willingness to repay, risk synthesis, compliance status, and final recommendation
6. Optionally audits all requests/responses to PostgreSQL for governance

### Key Components

**`app/main.py`** - FastAPI application with:
- `GET /health` - Health check endpoint
- `POST /v1/analyze` - Main analysis endpoint; handles correlation IDs, validation, auditing, error handling
- `synthesize_fallback()` - Heuristic mock synthesis when MOCK_MODE=true
- Prometheus metrics auto-instrumentation

**`app/models.py`** - Pydantic schemas:
- `QSEReportInput` - Input schema accepting 10+ data category sections from QSE (affordability, credit performance, fraud signals, behavioral intelligence, etc.)
- `QAAQualitativeReport` - Output schema with 8 narrative fields + final recommendation enum
- Nested models for SHAP, risk scenarios, NBE compliance
- Uses `extra="ignore"` to tolerate QSE schema evolution

**`app/gemini_client.py`** - AI integration:
- Configures google-generativeai SDK with API key and model
- `run_gemini()` - Async function with retry/backoff (3 attempts), timeout (12s default), and JSON Mode generation
- `build_prompt()` - Constructs persona-driven prompt for CrediSynth analyst role
- Raises `DownstreamError` on failures for proper HTTP 503 handling

**`app/db.py`** - Async PostgreSQL auditing:
- Uses SQLAlchemy 2.0 async with asyncpg driver
- `AnalysisRecord` table stores analysis_id, correlation_id, status, request/response JSON, error text, timestamps
- `init_db()` - Auto-creates database if missing (requires privileges), creates tables
- `audit_created()`, `audit_completed()`, `audit_failed()` - Lifecycle tracking
- Auditing is optional; service operates without DB if DATABASE_URL not set

**`app/config.py`** - Environment configuration via python-dotenv:
- GEMINI_API_KEY, GEMINI_MODEL, MOCK_MODE, REQUEST_TIMEOUT_SECONDS, DATABASE_URL
- Settings class provides typed access to env vars with sensible defaults

### Data Flow Detail
- Input: 164+ feature credit report with sections like `affordability_and_obligations`, `core_credit_performance`, `identity_and_fraud_intelligence`, `behavioral_intelligence`, `contextual_and_macroeconomic_factors`
- Mapping: capacity (DTI, residual income, salary consistency) → ability_to_repay; delinquency history, behavioral scores → willingness_to_repay; inflation, sector risk → key_risk_synthesis
- Output: 4 narrative fields (executive summary, ability, willingness, risks, strengths) + compliance summary + final recommendation (Approve | Approve with Conditions | Manual Review | Decline) + justification

### Design Principles
1. **Decoupled**: QAA does not compute scores; only synthesizes existing QSE output
2. **Observability**: Correlation IDs flow through all logs/audit; Prometheus metrics at /metrics
3. **Resilience**: Retry logic with exponential backoff; circuit breaker pattern for AI calls; graceful degradation to mock mode
4. **Governance**: Immutable audit trail; prompt/model version tracking (future); NBE compliance enforcement
5. **Forward Compatibility**: `extra="ignore"` in Pydantic allows QSE to add fields without breaking QAA

## Development Notes

### Testing Strategy
- No formal test framework is currently configured (no pytest.ini or test files)
- Test manually using sample_request.json and the example outputs in examples/ directory
- Verify mock mode behavior: set MOCK_MODE=true and POST sample_request.json to confirm heuristic fallback
- Test Gemini integration: set MOCK_MODE=false with valid GEMINI_API_KEY and validate JSON Mode response
- Golden tests mentioned in design doc (Section 11) are planned but not yet implemented

### Mock Mode vs. AI Mode
- **MOCK_MODE=true**: Uses `synthesize_fallback()` function with simple heuristics (DTI < 0.35, residual income > 5000, verified Fayda → "Approve with Conditions")
- **MOCK_MODE=false**: Calls Gemini 1.5 Pro with JSON Mode; requires GEMINI_API_KEY
- Mock mode is the default for local development and Docker to avoid API costs

### Database Setup
- Optional: Service runs without DATABASE_URL (auditing disabled)
- If DATABASE_URL is set, service auto-creates database and tables on startup
- Example: `postgresql://user:pass@localhost:5432/credisynth`
- Must use asyncpg driver for async engine; db.py auto-converts standard postgres:// URLs to postgresql+asyncpg://

### Adding New Features
- To add input fields: extend sections in `app/models.py` `QSEReportInput` (dicts tolerate any structure)
- To modify output: update `QAAQualitativeReport` schema; update Gemini prompt in `gemini_client.py` to match
- To adjust recommendations: modify heuristic logic in `synthesize_fallback()` for mock mode; adjust Gemini prompt for AI mode
- Prompt versioning and model versioning planned but not yet implemented (see Section 12 in design doc)

### Error Handling
- 400: Malformed JSON body
- 422: Valid JSON but fails Pydantic validation (missing required fields)
- 503: Gemini API unavailable/timeout/invalid response; includes retries
- 500: Unexpected internal errors
- All errors logged with correlation_id; audit_failed() called to record in DB

### Security Considerations
- Never commit .env files with real GEMINI_API_KEY
- Use .env.example as template; actual .env should be gitignored
- Future: OAuth2/mTLS for client authentication (not yet implemented)
- Future: TLS termination at ingress (deployment phase)
- PII minimization: only store identifiers in audit DB

### Design Documents
- `CrediSynth_QAA_System_Design.md` - Full system design with 21 sections covering architecture, schemas, prompt engineering, governance, rollout
- `PLAN.md` - Execution milestones M0-M8 from design to scale
- `openapi/openapi.yaml` - OpenAPI 3.0 spec for API contract
- `examples/qaa_output_example.json` - Reference output for golden testing
- `sample_request.json` - 164-feature example QSE input

### Configuration
All config is environment-driven; no config files. Key variables:
- `MOCK_MODE`: true (heuristic) | false (Gemini)
- `GEMINI_API_KEY`: Required when MOCK_MODE=false
- `GEMINI_MODEL`: Defaults to gemini-1.5-pro
- `REQUEST_TIMEOUT_SECONDS`: Timeout for Gemini calls (default 12s)
- `DATABASE_URL`: Optional Postgres URL for auditing
- `APP_NAME`, `APP_VERSION`: Metadata for /health endpoint
