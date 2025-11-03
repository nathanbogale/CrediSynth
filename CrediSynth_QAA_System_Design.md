# CrediSynth QAA — System Design

## 1. Executive Summary
- Purpose: Provide expert-in-the-loop qualitative reasoning for loan decisions by synthesizing complex quantitative outputs from the Quantitative Scoring Engine (QSE).
- Scope: Consumes the full QSE JSON output (scores, SHAP, risk scenarios, NBE compliance), produces a concise, auditable qualitative report for loan officers and credit committees.
- Positioning: Decoupled service; does not compute scores. Operates API-first, enabling explainable decisions and governance.
- Outcomes: Faster decisions, consistent narratives across cases, robust audit trail, compliance alignment, and operational SLAs.

## 2. Architecture
- Components:
  - `QAA API` (FastAPI): Validates input, orchestrates Gemini calls, returns qualitative JSON.
  - `Validation Layer` (Pydantic): Strict schema validation with `extra="ignore"` to tolerate forward-compatible fields.
  - `Gemini Client` (google-generativeai): JSON Mode output; constrained persona; deterministic-ish settings.
  - `Audit DB` (Postgres): Logs requests, responses, events, errors, prompt/model versions for governance.
  - `Observability` (OpenTelemetry, Prometheus/Grafana): Traces, metrics, logs.
  - `Secrets/Config` (Kubernetes Secrets/ConfigMaps): API keys, model/prompt versions, feature flags.

- Flow:
  - Your App → QSE → Complex JSON
  - Your App → `POST /v1/analyze` (QSE JSON)
  - QAA API → Gemini API → Gemini JSON response
  - QAA API → Returns `QAAQualitativeReport` JSON

- Data movement is synchronous for P95 latency targets. Optional async job mode can be added later if needed.

## 3. Technology Stack
- API: `FastAPI` (Python 3.11+)
- AI: `google-generativeai` (Gemini 1.5 Pro in JSON Mode)
- Validation: `Pydantic v2`
- Database: `Postgres` (with migrations via Alembic)
- Container/Orchestration: `Docker` / `Kubernetes`
- Observability: `OpenTelemetry`, `Prometheus`, `Grafana`
- Security: TLS everywhere, OAuth2/mTLS service-to-service, secrets via K8s Secrets

## 4. API Design
- Endpoint: `POST /v1/analyze`
- Auth: Bearer token (OAuth2 client credentials) or mTLS; enforce `correlation_id` header for traceability.
- Idempotency: Respect `request_id` from QSE; optionally accept `Idempotency-Key` header.
- Rate limiting: Configurable per client; respond with `429` when exceeded.

### 4.1 Request and Response
- Request Body: `QSEReportInput` (validated; unknown fields ignored)
- Success `200`: `QAAQualitativeReport`
- Error Responses:
  - `400 Bad Request`: Malformed JSON
  - `422 Unprocessable Entity`: Valid JSON but fails validation
  - `503 Service Unavailable`: Gemini downstream failure/unavailable

### 4.2 Example Usage
```
POST /v1/analyze
Authorization: Bearer <token>
X-Correlation-Id: corr_complete_164_test_001
Content-Type: application/json
```
Body: contents of `sample_request.json` (QSE expected response)

Success `200` response (example):
```json
{
  "analysis_id": "qaa_20251009_000123",
  "qse_request_id": "test_complete_164_features_001",
  "customer_id": "customer_complete_164_test_001",
  "executive_summary": "Applicant shows strong income stability and clean payment history. ...",
  "ability_to_repay": "DTI and residual income indicate sufficient buffer, with consistent salary inflow and low volatility.",
  "willingness_to_repay": "Behavioral metrics and delinquency records suggest high intent to repay; peer vouching present.",
  "key_risk_synthesis": "Exposure to inflation and sector cyclicality. Monitor mobile money volatility and overdraft usage.",
  "key_strengths_synthesis": "Verified identity, stable income, positive savings behavior, on-time utility and telecom payments.",
  "nbe_compliance_summary": "COMPLIANT",
  "final_recommendation": "Approve with Conditions",
  "recommendation_justification": "Approval contingent on moderate inflation exposure and sector cyclicality. Strong capacity and intent."
}
```

## 5. Schemas

### 5.1 Input Schema: `QSEReportInput` (conceptual)
```python
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class ShapFactor(BaseModel):
    name: str
    impact: float  # positive increases approval likelihood; negative reduces
    direction: str  # "positive" | "negative"

class ShapAnalysis(BaseModel):
    risk_factors: List[ShapFactor] = []
    confidence_factors: List[ShapFactor] = []
    global_importance_order: Optional[List[str]] = None

class RiskScenario(BaseModel):
    name: str
    description: str
    severity: str  # e.g., "Low" | "Medium" | "High"

class RiskAnalysis(BaseModel):
    scenarios: List[RiskScenario] = []
    default_probability: Optional[float] = None

class NBECompliance(BaseModel):
    status: str  # "COMPLIANT" | "NON_COMPLIANT"
    reasons: List[str] = []

class AdditionalInsights(BaseModel):
    notes: Optional[str] = None
    tags: List[str] = []

class QSEReportInput(BaseModel):
    request_id: str
    customer_id: str
    credit_score: Optional[float] = None
    risk_level: Optional[str] = None
    default_probability: Optional[float] = None
    model_version: str
    features_count: Optional[int] = None

    feature_analysis: Dict[str, Any] = {}
    explainability: Optional[ShapAnalysis] = None
    risk_analysis: Optional[RiskAnalysis] = None
    nbe_compliance_status: Optional[NBECompliance] = None
    additional_insights: Optional[AdditionalInsights] = None

    class Config:
        extra = "ignore"  # tolerate QSE evolution without breaking QAA
```

### 5.2 Output Schema: `QAAQualitativeReport`
```python
from typing import Literal
from pydantic import BaseModel, Field

class QAAQualitativeReport(BaseModel):
    analysis_id: str = Field(..., description="Unique ID for this QAA transaction")
    qse_request_id: str = Field(..., description="Original 'request_id' from QSE report")
    customer_id: str = Field(..., description="Customer ID from QSE report")

    executive_summary: str = Field(..., description="3–4 sentence C-level summary")
    ability_to_repay: str = Field(..., description="Plain-English capacity analysis")
    willingness_to_repay: str = Field(..., description="Plain-English intent analysis")
    key_risk_synthesis: str = Field(..., description="Actionable warning synthesis")
    key_strengths_synthesis: str = Field(..., description="Positive factors synthesis")
    nbe_compliance_summary: str = Field(..., description="'COMPLIANT' or 'NON-COMPLIANT: [Reason]'")

    final_recommendation: Literal['Approve', 'Approve with Conditions', 'Manual Review', 'Decline']
    recommendation_justification: str = Field(..., description="Final paragraph justification")
```

## 6. Core Service Logic — Gemini Agent

### 6.1 Persona & Guardrails
- Persona: "CrediSynth," a senior risk analyst at NBE with 20 years of experience.
- Constraints:
  - Use only the provided QSE JSON; do not invent data.
  - Output strictly matches `QAAQualitativeReport` schema in JSON Mode.
  - Avoid boilerplate; be concise and decisive with clear rationale.
  - Respect compliance signals; if non-compliant, state reasons plainly.

### 6.2 Prompt Template (JSON Mode)
```text
System: You are CrediSynth, a senior risk analyst at the National Bank of Ethiopia. Your job is to synthesize the QSE JSON into a concise and actionable qualitative report for a loan officer. Use only the provided data. Output valid JSON that conforms exactly to the QAAQualitativeReport schema.

User content:
- qse_request_id: {{request_id}}
- customer_id: {{customer_id}}
- risk_level: {{risk_level}}
- default_probability: {{default_probability}}
- model_version: {{model_version}}
- nbe_compliance_status: {{nbe_compliance_status.status}}; reasons: {{nbe_compliance_status.reasons}}
- SHAP risk_factors (top): {{explainability.risk_factors}}
- SHAP confidence_factors (top): {{explainability.confidence_factors}}
- risk scenarios: {{risk_analysis.scenarios}}
- key feature_analysis highlights: {{feature_analysis_summary}}

Required JSON fields to produce:
{
  "analysis_id": "<generate unique>",
  "qse_request_id": "{{request_id}}",
  "customer_id": "{{customer_id}}",
  "executive_summary": "<3–4 sentences>",
  "ability_to_repay": "<capacity synthesis>",
  "willingness_to_repay": "<intent synthesis>",
  "key_risk_synthesis": "<actionable warning>",
  "key_strengths_synthesis": "<positive factors>",
  "nbe_compliance_summary": "<COMPLIANT | NON-COMPLIANT: [Reason]>",
  "final_recommendation": "<Approve | Approve with Conditions | Manual Review | Decline>",
  "recommendation_justification": "<final paragraph>"
}
```

### 6.3 Invocation Settings
- Model: `gemini-1.5-pro`
- Generation config: `temperature=0.2`, `top_p=0.9`, `top_k=40`, `max_output_tokens≈1024`
- JSON Mode: enabled with structured output expectation
- Safety: default safety settings; consider stricter thresholds as needed
- Timeouts: `client_timeout=8s`; total request budget `10–12s`

### 6.4 Response Handling
- Parse as JSON; validate against `QAAQualitativeReport`
- If validation fails: retry with a corrective system nudge (max 1 retry), else `503`
- Attach `analysis_id` (UUIDv7) if model does not provide one

### 6.5 Error Strategy
- Retry/backoff on `429/5xx` with jitter (e.g., `200ms → 500ms`)
- Circuit breaker after consecutive failures; degrade to `Manual Review` response (configurable) or `503`
- Categorize errors: client (400/422), validation (422), downstream (503), internal (500)

## 7. Data & Storage Design (Postgres)

### 7.1 Tables
- `analyses`
  - `id` (pk, uuid), `analysis_id` (unique), `qse_request_id`, `customer_id`
  - `status` (created|processing|completed|failed)
  - `risk_level`, `default_probability`, `model_version`, `prompt_version`, `gemini_model`
  - `final_recommendation`, `nbe_compliance_summary`
  - `created_at`, `completed_at`, `correlation_id`

- `analysis_payloads`
  - `analysis_id` (fk), `qse_payload_jsonb`, `qaa_output_jsonb`

- `analysis_events`
  - `id` (pk), `analysis_id` (fk), `event_type`, `event_jsonb`, `created_at`

- `errors`
  - `id` (pk), `analysis_id` (nullable), `code`, `message`, `details_jsonb`, `created_at`

- Indexes: `idx_analyses_request_id`, `idx_analyses_customer_id`, `idx_analyses_created_at`

### 7.2 Governance & Retention
- PII minimization: store only required identifiers
- Encryption at rest (Postgres + volume), TLS in transit
- Retention policies: configurable (e.g., 24 months)
- Full auditability: every change/event recorded with correlation IDs

## 8. Observability
- Logs: structured JSON with `request_id`, `correlation_id`, `analysis_id`, latency, error codes
- Metrics: request count, latency percentiles, error rate, Gemini latency, retry counts, compliance rate distribution
- Tracing: OTel spans across API → validation → Gemini → DB

## 9. Security & Compliance
- AuthN/Z: OAuth2 client credentials or mTLS with allowlists
- TLS termination: Ingress with enforced modern ciphers
- Secrets: `GEMINI_API_KEY`, DB creds via K8s Secrets
- NBE compliance: reflect `nbe_compliance_status`; block approval if non-compliant (policy-configurable)
- Audit: immutable logs, access controls, periodic reviews

## 10. Deployment & Ops
- Docker: Python slim image; non-root user; health checks
- Kubernetes:
  - `Deployment` with HPA (CPU/memory-based, plus custom QPS metric)
  - `PodDisruptionBudget`, `ResourceQuota`, `NetworkPolicy`
  - `readinessProbe` (DB + Gemini warmup), `livenessProbe`
- Release: blue/green or canary with metric gates; rollout/rollback via CI
- Config: environment-driven (`QAA_PROMPT_VERSION`, `GEMINI_MODEL`, feature flags)

## 11. Testing Strategy
- Unit: schema validation, sanitization, decision mapping logic
- Integration: Gemini client stub/mocks; error paths; retries
- Golden tests: fixed QSE inputs → expected qualitative outputs (allow minor wording variance via regex anchors)
- E2E: deployed environment, tracing checks, DB asserts
- Chaos: simulate Gemini outage to validate circuit breaker and error surfaces

## 12. Versioning & Compatibility
- API versions: prefix paths (`/v1`), additive changes only inside version
- Prompt versioning: `QAA_PROMPT_VERSION` stored with each analysis
- Backward compatibility: `extra="ignore"` for QSE input; deprecation policy with timelines

## 13. Implementation Skeleton (Illustrative)
```python
# fastapi_app.py
from fastapi import FastAPI, HTTPException, Header
from pydantic import ValidationError
import uuid

app = FastAPI()

@app.post("/v1/analyze")
async def analyze(qse: QSEReportInput, x_correlation_id: str = Header(None)):
    analysis_id = str(uuid.uuid4())
    # persist created status
    try:
        qaa = await run_gemini(qse, analysis_id)
    except DownstreamError as e:
        # persist error
        raise HTTPException(status_code=503, detail="Gemini unavailable")
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    # persist completed + payloads
    return qaa
```

```python
# gemini_client.py
import google.generativeai as genai

def configure(api_key: str, model: str = "gemini-1.5-pro"):
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model)

async def run_gemini(qse: QSEReportInput, analysis_id: str) -> QAAQualitativeReport:
    model = configure(api_key=os.getenv("GEMINI_API_KEY"))
    prompt = build_prompt(qse, analysis_id)
    resp = await model.generate_content(prompt, generation_config={
        "temperature": 0.2,
        "max_output_tokens": 1024,
        "response_mime_type": "application/json",
    })
    data = resp.text  # JSON Mode returns JSON text
    qaa = QAAQualitativeReport.model_validate_json(data)
    if not qaa.analysis_id:
        qaa.analysis_id = analysis_id
    return qaa
```

## 14. Rollout Plan
- Phase 1: Internal testing with sampled QSE outputs; tune prompt
- Phase 2: Pilot with small loan officer group; gather feedback
- Phase 3: Expand usage; enable HPA; set SLAs and SLOs
- Phase 4: Formalize compliance sign-offs, add model/prompt governance cadence

## 15. Appendix

### 15.1 Example Input
- Use `t:\CrediSynth\sample_request.json` as a representative QSE input payload during development and testing.

### 15.2 Example `curl`
```
curl -X POST https://qaa.yourdomain/v1/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Correlation-Id: corr_complete_164_test_001" \
  -H "Content-Type: application/json" \
  --data-binary @t:/CrediSynth/sample_request.json
```

---

This document provides the end-to-end system design for the CrediSynth QAA service, including architecture, data contracts, agent design, governance, and operational plans. Next steps: scaffold the FastAPI project, implement schemas, integrate Gemini, and set up DB migrations and observability.

## 16. Field Mapping to QSE Input
- Capacity (ability_to_repay):
  - `affordability_and_obligations.monthly_income_etb`, `debt_to_income_ratio`, `residual_income_etb`, `residual_income_ratio`, `projected_installment`, `cash_buffer_days`, `income_stability_cv_6m`, `existing_loan_count_open`, `credit_utilization_ratio`, `income_verification_status`.
- Liquidity & cash flow (supporting capacity):
  - `bank_and_mobile_money_dynamics.salary_inflow_consistency_score`, `average_daily_balance_90d`, `net_inflow_volatility_90d`, `overdraft_usage_days_90d`, `nsf_count_6m`, `nsf_frequency_6m`, `mobile_money_in_out_ratio`.
- Intent (willingness_to_repay):
  - `core_credit_performance.worst_status_last_12m`, delinquency counts, `recent_hard_inquiries_12m`, `grace_days_used_avg`, `rent_on_time_rate_12m`, `behavioral_intelligence.behavioral_consistency_score`, `conscientiousness_score`, `peer_vouching_count`, `online_reputation_score`.
- Identity & fraud:
  - `identity_and_fraud_intelligence.fayda_verification_status`, `kyc_level`, `pep_or_sanctions_hit_flag`, `is_device_emulator`, `device_compromise_status`, `biometric_liveness_check_status`, `address_verification_status`, `document_expiry_days`, `device_id_consistency_score`, `sim_swap_recent_flag`.
- External & macro risks (risk synthesis):
  - `contextual_and_macroeconomic_factors.inflation_rate_recent`, `sector_cyclicality_index`, `regional_unemployment_rate`, `exchange_rate_12m_change`, `energy_blackout_days_90d`, `conflict_risk_index`.
- Product context:
  - `product_specific_intelligence.product_type`, `loan_to_income_ratio_lti`, `debt_service_to_income_ratio_dsti`, collateral fields.
- Digital behavioral signals:
  - `digital_behavioral_intelligence.savings_behavior_score`, `discretionary_spend_ratio_90d`, `app_engagement_frequency_30d`, `push_notification_interaction_rate`, `momo_cash_out_velocity_48hr`, `weekend_social_spending_volatility`.
- Governance/meta:
  - `model_governance_and_monitoring.model_version`, `reason_codes_top_3`, `final_risk_level`, `model_confidence_score`, `timestamp`.

## 17. OpenAPI Draft (Excerpt)
```yaml
openapi: 3.0.3
info:
  title: CrediSynth QAA API
  version: 1.0.0
paths:
  /v1/analyze:
    post:
      summary: Analyze QSE report and return qualitative synthesis
      operationId: analyzeQSEReport
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/QSEReportInput'
      responses:
        '200':
          description: Qualitative synthesis
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/QAAQualitativeReport'
        '400': { description: Malformed JSON }
        '422': { description: Validation failed }
        '503': { description: Downstream Gemini unavailable }
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
  schemas:
    QSEReportInput:
      type: object
      additionalProperties: true
      required: [request_id, customer_id, model_version]
    QAAQualitativeReport:
      type: object
      required:
        [analysis_id, qse_request_id, customer_id, executive_summary,
         ability_to_repay, willingness_to_repay, key_risk_synthesis,
         key_strengths_synthesis, nbe_compliance_summary,
         final_recommendation, recommendation_justification]
```

## 18. Error Catalog
- `QAA-400-JSON_MALFORMED`: Body cannot be parsed as JSON; advise client to fix payload.
- `QAA-422-VALIDATION_FAILED`: Parsed JSON but missing/invalid fields for `QSEReportInput`.
- `QAA-503-GEMINI_UNAVAILABLE`: Downstream AI call failed or timed out; retry recommended.
- `QAA-500-INTERNAL_ERROR`: Unexpected server error; logged with correlation ID.

## 19. Threat Model Summary
- Risks: leaked API keys, prompt injection via QSE payload, PII exposure in logs, replay attacks.
- Mitigations:
  - Secrets in K8s, rotation policies, restricted IAM.
  - Sanitize and bound QSE payload into prompt (no code execution, JSON-only mode).
  - Structured logs without sensitive fields; encrypted DB volumes.
  - Idempotency keys and anti-replay checks with short-lived tokens.

## 20. Implementation Checklist
- FastAPI skeleton with `/v1/analyze` and health endpoints.
- Pydantic models (input/output) and validators.
- Gemini client with JSON Mode, retries, circuit breaker.
- Postgres tables and migrations; async persistence.
- Observability integration (logs, metrics, traces).
- Security headers, auth middleware, rate limiting.
- Test suite: unit, integration (mock Gemini), golden narratives.

## 21. Example Output (Derived from `sample_request.json`)
```json
{
  "analysis_id": "qaa_20251009_000987",
  "qse_request_id": "test_complete_164_features_001",
  "customer_id": "customer_complete_164_test_001",
  "executive_summary": "Applicant exhibits strong capacity and verified identity, with consistent salary inflows and low delinquency. Macroeconomic inflation and sector cyclicality present moderate external risk, but residual income and cash buffers are adequate. Recommendation: approve with conditions focused on monitoring liquidity and spending patterns.",
  "ability_to_repay": "Residual income of ETB 8,500 and low installment-to-income ratio (0.08) indicate ample buffer. Salary inflow consistency (85.5) and average daily balance of ETB 8,500 support stable cash flows; overdraft usage is limited (5 days) and NSF events are rare (1 in 6 months).",
  "willingness_to_repay": "Clean recent payment history with zero 30/60/90-day delinquencies and verified KYC/fayda. Behavioral consistency (75.5), conscientiousness (78), and peer vouching (2) suggest high intent to repay; rent and utilities show on-time behavior (≥0.95).",
  "key_risk_synthesis": "External inflation (18.5%) and sector cyclicality (45) may pressure affordability; modest weekend social spending volatility (0.22) and mobile money velocity (0.25) warrant monitoring. Overdraft usage (5 days) is present but contained.",
  "key_strengths_synthesis": "Verified identity and enhanced KYC, stable income with consistent deposits, strong savings behavior (72.5), positive on-time utility and telecom payment rates, and low DTI/residual income strength.",
  "nbe_compliance_summary": "COMPLIANT",
  "final_recommendation": "Approve with Conditions",
  "recommendation_justification": "Approve given strong capacity, verified identity, and positive behavioral indicators. Set conditions: monitor cash flow volatility and overdraft usage; reassess affordability if inflation materially increases."
}
```