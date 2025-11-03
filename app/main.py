import uuid
import os
import logging
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException, Header, Request, Body
from pydantic import ValidationError

from .models import QSEReportInput, QAAQualitativeReport
from .config import settings
from .gemini_client import run_gemini, DownstreamError
from .db import init_db, audit_created, audit_completed, audit_failed, has_db

from prometheus_fastapi_instrumentator import Instrumentator


logger = logging.getLogger(__name__)


app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)
try:
    Instrumentator().instrument(app).expose(app)
except RuntimeError as e:
    # If running under reload or late in lifecycle, avoid startup failure
    logger.warning(f"Prometheus instrumentation skipped: {e}")


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}


def synthesize_fallback(qse: QSEReportInput, analysis_id: str) -> QAAQualitativeReport:
    aff = qse.affordability_and_obligations or {}
    bank = qse.bank_and_mobile_money_dynamics or {}
    core = qse.core_credit_performance or {}
    beh = qse.behavioral_intelligence or {}
    fraud = qse.identity_and_fraud_intelligence or {}
    ctx = qse.contextual_and_macroeconomic_factors or {}

    dti = aff.get("debt_to_income_ratio")
    residual_income = aff.get("residual_income_etb")
    salary_consistency = bank.get("salary_inflow_consistency_score")
    delinquency_30 = core.get("delinquency_30d_count_12m")
    kyc = fraud.get("kyc_level")
    fayda = fraud.get("fayda_verification_status")
    pep_hit = fraud.get("pep_or_sanctions_hit_flag")
    savings_score = (qse.digital_behavioral_intelligence or {}).get("savings_behavior_score")

    compliant = (pep_hit is False) and (kyc in ("Enhanced", "Standard")) and (fayda == "Verified") and (aff.get("debt_service_to_income_ratio_dsti", 1) <= 0.35)
    nbe_summary = "COMPLIANT" if compliant else "NON-COMPLIANT: Policy thresholds not met or KYC/Fayda issues"

    if (dti is not None and dti < 0.35) and (residual_income or 0) > 5000 and fayda == "Verified":
        final = "Approve with Conditions"
    else:
        final = "Manual Review"

    exec_summary = (
        "Applicant shows solid repayment capacity with verified identity. "
        "DTI and residual income indicate adequate buffer; salary inflows are consistent. "
        "External macro risks exist but are moderate."
    )

    ability = (
        f"Residual income {residual_income} ETB and DTI {dti} suggest capacity. "
        f"Salary consistency {salary_consistency} and limited overdraft/NSF support stable cash flow."
    )

    willingness = (
        f"Recent delinquency counts are low ({delinquency_30}). "
        f"Behavioral consistency {beh.get('behavioral_consistency_score')} and conscientiousness {beh.get('conscientiousness_score')} indicate intent to repay."
    )

    risks = (
        f"Inflation {ctx.get('inflation_rate_recent')}% and sector cyclicality {ctx.get('sector_cyclicality_index')} pose moderate risk; "
        f"monitor overdraft usage and social spending volatility."
    )

    strengths = (
        f"Verified identity ({fayda}), KYC {kyc}, consistent deposits, savings behavior {savings_score}, on-time utilities/telecom."
    )

    justification = (
        "Approve with conditions given strong capacity and verified identity; "
        "monitor liquidity and spending volatility; reassess if inflation worsens."
        if final == "Approve with Conditions"
        else "Manual review advised due to capacity/compliance uncertainties."
    )

    return QAAQualitativeReport(
        analysis_id=analysis_id,
        qse_request_id=qse.request_id,
        customer_id=qse.customer_id,
        executive_summary=exec_summary,
        ability_to_repay=ability,
        willingness_to_repay=willingness,
        key_risk_synthesis=risks,
        key_strengths_synthesis=strengths,
        nbe_compliance_summary=nbe_summary,
        final_recommendation=final,
        recommendation_justification=justification,
    )


_ROOT = Path(__file__).resolve().parents[1]
try:
    SAMPLE_REQ = json.loads((_ROOT / "sample_request.json").read_text(encoding="utf-8"))
except Exception:
    SAMPLE_REQ = None
try:
    SAMPLE_RESP = json.loads((_ROOT / "examples" / "qaa_output_example.json").read_text(encoding="utf-8"))
except Exception:
    SAMPLE_RESP = None


@app.post(
    "/v1/analyze",
    responses={
        200: {
            "description": "Qualitative synthesis from QSE report",
            "content": {"application/json": {"example": SAMPLE_RESP or {}}},
        },
        422: {"description": "Validation error"},
        503: {"description": "Downstream AI unavailable or invalid response"},
        500: {"description": "Internal server error"},
    },
)
async def analyze(
    request: Request,
    qse: QSEReportInput = Body(
        ..., examples={
            "complete_sample": {
                "summary": "Complete sample aligned to QSE output",
                "value": SAMPLE_REQ or {
                    "request_id": "sample",
                    "customer_id": "cust",
                },
            }
        }
    ),
    x_correlation_id: str | None = Header(None),
):
    analysis_id = str(uuid.uuid4())
    correlation_id = x_correlation_id or request.headers.get("X-Correlation-ID") or str(uuid.uuid4())

    # Audit created
    try:
        await audit_created(analysis_id, correlation_id, qse.model_dump())
    except Exception as e:
        logger.warning(f"Audit create failed: {e}")

    try:
        # Honor MOCK_MODE strictly: only use fallback when explicitly enabled
        if settings.MOCK_MODE:
            qaa = synthesize_fallback(qse, analysis_id)
        else:
            qaa = await run_gemini(qse, analysis_id)
    except DownstreamError as e:
        # Audit fail then raise
        try:
            await audit_failed(analysis_id, str(e))
        except Exception as ie:
            logger.warning(f"Audit failed write error: {ie}")
        # Surface the actual downstream error message to aid debugging
        raise HTTPException(status_code=503, detail=str(e))
    except ValidationError as e:
        try:
            await audit_failed(analysis_id, str(e))
        except Exception as ie:
            logger.warning(f"Audit failed write error: {ie}")
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        try:
            await audit_failed(analysis_id, str(e))
        except Exception as ie:
            logger.warning(f"Audit failed write error: {ie}")
        raise HTTPException(status_code=500, detail="Internal server error")

    # Audit completed
    try:
        await audit_completed(analysis_id, qaa.model_dump())
    except Exception as e:
        logger.warning(f"Audit complete failed: {e}")

    return qaa


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=4000, reload=True)


@app.on_event("startup")
async def _startup():
    # Initialize DB if configured — do not block app startup on DB failures
    try:
        await init_db()
    except Exception as e:
        logger.warning(f"DB init failed; auditing disabled: {e}")

    # Prometheus metrics already configured at import-time