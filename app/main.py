import uuid
import os
import logging
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException, Header, Request, Body
from pydantic import ValidationError

from .models import (
    QSEReportInput,
    QAAQualitativeReport,
    QAAExtendedResponse,
    QAAExtendedResponseV1_1,
    Scores,
    ExplainabilityExtended,
    ShapAnalysisExtended,
    RiskAnalysisExtended,
    RiskScenarioExtended,
    RiskDimensions,
    EnsembleDetails,
    NBEComplianceStatusExtended,
    ProcessingMetadata,
    AdditionalInsightsExtended,
)
from .config import settings
from .gemini_client import run_gemini, DownstreamError
from .explainability_client import fetch_explainability
from .db import init_db, audit_created, audit_completed, audit_failed, has_db, get_analysis

from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Counter, Histogram


logger = logging.getLogger(__name__)


app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)
try:
    Instrumentator().instrument(app).expose(app)
except RuntimeError as e:
    # If running under reload or late in lifecycle, avoid startup failure
    logger.warning(f"Prometheus instrumentation skipped: {e}")

# Custom metrics
REQ_COUNTER = Counter("qaa_requests_total", "Total analyze requests", ["status"]) 
PROC_TIME_SEC = Histogram("qaa_processing_time_seconds", "Analyze processing time (seconds)")


@app.get("/health", tags=["Health"], summary="Service health")
async def health():
    status = "ok"
    # Degrade-aware: if downstream disabled or DB missing, reflect but remain 200
    details = {
        "db": "enabled" if has_db() else "disabled",
        "mock_mode": settings.MOCK_MODE,
    }
    return {"status": status, "version": settings.APP_VERSION, "details": details}


@app.get("/ready", tags=["Health"], summary="Service readiness")
async def ready():
    # Check DB readiness (if configured) and minimal model availability
    if has_db():
        db_ready = True
    else:
        db_ready = True  # treat as ready when DB auditing disabled
    model_ready = True  # Placeholder: could check model cache or client ping
    ready = db_ready and model_ready
    return {"ready": ready, "db_ready": db_ready, "model_ready": model_ready}


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
    response_model=QAAExtendedResponse,
    responses={
        200: {
            "description": "Extended qualitative synthesis from QSE report",
            "content": {"application/json": {"example": SAMPLE_RESP or {}}},
        },
        422: {"description": "Validation error"},
        503: {"description": "Downstream AI unavailable or invalid response"},
        500: {"description": "Internal server error"},
    },
    tags=["Analysis"],
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

    import time
    start_ms = int(time.time() * 1000)
    logger.info(json.dumps({"event": "analyze_start", "analysis_id": analysis_id, "correlation_id": correlation_id}))
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
        REQ_COUNTER.labels(status="downstream_error").inc()
        raise HTTPException(status_code=503, detail=str(e))
    except ValidationError as e:
        try:
            await audit_failed(analysis_id, str(e))
        except Exception as ie:
            logger.warning(f"Audit failed write error: {ie}")
        REQ_COUNTER.labels(status="validation_error").inc()
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        try:
            await audit_failed(analysis_id, str(e))
        except Exception as ie:
            logger.warning(f"Audit failed write error: {ie}")
        REQ_COUNTER.labels(status="internal_error").inc()
        raise HTTPException(status_code=500, detail="Internal server error")

    # Build extended response using QSE input and QAA qualitative report
    def _derive_risk_category(risk_level: str | None, default_prob: float | None) -> str | None:
        if isinstance(risk_level, str) and risk_level:
            s = risk_level.strip().lower()
            if s in ("low", "medium", "high"):
                return s.capitalize()
        if default_prob is not None:
            try:
                # Map default probability to a category threshold
                if default_prob < 0.1:
                    return "Low"
                if default_prob < 0.25:
                    return "Medium"
                return "High"
            except Exception:
                pass
        return None

    def _clamp_credit_score(score: float | int | None) -> int | None:
        if score is None:
            return None
        try:
            val = int(round(float(score)))
            return max(300, min(850, val))
        except Exception:
            return None

    # Prefer top-level default_probability; add layered fallbacks
    governance = qse.model_governance_and_monitoring or {}
    digital = qse.digital_behavioral_intelligence or {}

    # Effective risk level: use top-level or governance-provided final_risk_level
    effective_risk_level = qse.risk_level or governance.get("final_risk_level")

    default_prob = qse.default_probability
    if default_prob is None and qse.risk_analysis and qse.risk_analysis.default_probability is not None:
        default_prob = qse.risk_analysis.default_probability
    # Fallback to peer default rate from digital behavioral intelligence
    if default_prob is None:
        peer_dr = digital.get("anonymized_peer_default_rate")
        if isinstance(peer_dr, (int, float)):
            default_prob = float(peer_dr)

    # Final fallback: estimate from risk level mapping
    def _estimate_default_prob_from_level(level: str | None) -> float | None:
        if not isinstance(level, str) or not level:
            return None
        s = level.strip().lower()
        if s == "low":
            return 0.08
        if s == "medium":
            return 0.18
        if s == "high":
            return 0.35
        return None

    if default_prob is None:
        default_prob = _estimate_default_prob_from_level(effective_risk_level)

    risk_category = _derive_risk_category(effective_risk_level, default_prob)

    # Assemble structured explainability
    expl: ExplainabilityExtended | None = None
    if qse.explainability:
        expl = ExplainabilityExtended(
            shap_analysis=ShapAnalysisExtended(
                local_explanation=None,
                description=None,
                confidence_factors=qse.explainability.confidence_factors or [],
                risk_factors=qse.explainability.risk_factors or [],
            ),
            feature_importance=[],
            explanation_available=None,
            interpretation=None,
        )
    # Consolidate feature importance/global ordering if provided in feature_analysis
    if (qse.feature_analysis or {}).get("global_importance"):
        try:
            gi = qse.feature_analysis.get("global_importance")
            if isinstance(gi, list):
                expl = expl or ExplainabilityExtended()
                expl.shap_analysis = expl.shap_analysis or ShapAnalysisExtended()
                expl.shap_analysis.global_importance = [
                    {"feature": str(item.get("feature")), "importance": float(item.get("importance", 0.0))}
                    for item in gi if isinstance(item, dict)
                ]
                # top-N drivers by signed impact if available
                topn = sorted(expl.shap_analysis.global_importance, key=lambda x: x["importance"], reverse=True)[:5]
                expl.feature_importance = [
                    {"feature": t["feature"], "importance": t["importance"], "impact": "positive" if t["importance"] >= 0 else "negative"}
                    for t in topn
                ]
        except Exception:
            pass
    # Try external explainability service before falling back to heuristics
    if not expl:
        try:
            fetched = await fetch_explainability(qse)
            if fetched:
                expl = fetched
        except Exception:
            pass
    # Heuristic explainability builder when upstream explainability is absent
    if not expl:
        try:
            expl = ExplainabilityExtended(
                shap_analysis=ShapAnalysisExtended(),
                feature_importance=[],
                explanation_available=True,
                interpretation="Heuristic drivers computed from affordability, credit performance, and behavioral signals.",
            )
            # Build simple importance scores
            importance_entries = []
            dti = (qse.affordability_and_obligations or {}).get("debt_to_income_ratio")
            res_ratio = (qse.affordability_and_obligations or {}).get("residual_income_ratio")
            cash_days = (qse.affordability_and_obligations or {}).get("cash_buffer_days")
            del30 = (qse.core_credit_performance or {}).get("delinquency_30d_count_12m")
            beh_consistency = (qse.behavioral_intelligence or {}).get("behavioral_consistency_score")
            conscientious = (qse.behavioral_intelligence or {}).get("conscientiousness_score")
            savings = (qse.digital_behavioral_intelligence or {}).get("savings_behavior_score")

            if isinstance(dti, (int, float)):
                importance_entries.append({"feature": "debt_to_income_ratio", "importance": float(dti), "impact": "negative"})
            if isinstance(res_ratio, (int, float)):
                importance_entries.append({"feature": "residual_income_ratio", "importance": float(res_ratio), "impact": "positive" if res_ratio < 0.5 else "negative"})
            if isinstance(cash_days, (int, float)):
                # More cash buffer days is positive
                importance_entries.append({"feature": "cash_buffer_days", "importance": float(cash_days) / 90.0, "impact": "positive"})
            if isinstance(del30, (int, float)):
                importance_entries.append({"feature": "delinquency_30d_count_12m", "importance": float(del30) / 10.0, "impact": "negative"})
            if isinstance(beh_consistency, (int, float)):
                importance_entries.append({"feature": "behavioral_consistency_score", "importance": float(beh_consistency) / 100.0, "impact": "positive"})
            if isinstance(conscientious, (int, float)):
                importance_entries.append({"feature": "conscientiousness_score", "importance": float(conscientious) / 100.0, "impact": "positive"})
            if isinstance(savings, (int, float)):
                importance_entries.append({"feature": "savings_behavior_score", "importance": float(savings) / 100.0, "impact": "positive"})

            # Sort and take top-N
            importance_entries = sorted(importance_entries, key=lambda x: x["importance"], reverse=True)[:5]
            expl.feature_importance = importance_entries
            # Also populate a global importance list
            expl.shap_analysis.global_importance = [
                {"feature": e["feature"], "importance": e["importance"]} for e in importance_entries
            ]
        except Exception:
            pass

    # Assemble structured risk analysis
    risk_ext: RiskAnalysisExtended | None = None
    if qse.risk_analysis:
        scenarios: list[RiskScenarioExtended] = []
        for sc in qse.risk_analysis.scenarios or []:
            impact = sc.severity.lower() if isinstance(sc.severity, str) else "medium"
            scenarios.append(
                RiskScenarioExtended(
                    scenario=sc.name,
                    probability=None,
                    description=sc.description,
                    expected_default_rate=qse.risk_analysis.default_probability,
                    impact=impact,
                )
            )
        risk_ext = RiskAnalysisExtended(
            overall_risk_score=(qse.risk_analysis.default_probability * 100.0) if qse.risk_analysis.default_probability is not None else None,
            risk_dimensions=RiskDimensions(),
            risk_scenarios=scenarios,
            risk_mitigation=[],
            risk_factors=[],
            protective_factors=[],
        )

    # Derive consolidated scores
    def _load_platt_coeffs() -> tuple[float, float] | None:
        """Load Platt calibration coefficients from trained_models if available.

        Expect a JSON file with {"a": float, "b": float} representing the
        logistic calibration parameters such that calibrated = 1/(1+exp(a*x+b)).
        """
        try:
            calib_path = _ROOT / "trained_models" / "approval_probability_platt.json"
            if calib_path.exists():
                data = json.loads(calib_path.read_text())
                a = float(data.get("a"))
                b = float(data.get("b"))
                return a, b
        except Exception:
            return None
        return None

    def _apply_platt(p: float, coeffs: tuple[float, float] | None) -> float:
        import math
        if coeffs is None:
            return p
        a, b = coeffs
        # map base probability to logit domain approximately via inverse logit
        # then apply Platt transform; if p is 0 or 1, clamp slightly
        p = max(1e-6, min(1 - 1e-6, p))
        logit = math.log(p / (1 - p))
        calibrated = 1.0 / (1.0 + math.exp(a * logit + b))
        return max(0.0, min(1.0, calibrated))

    def _approval_probability_from(final_rec: str | None) -> float | None:
        if not isinstance(final_rec, str):
            return None
        s = final_rec.strip().lower()
        m = {
            "approve": 0.85,
            "approve with conditions": 0.65,
            "manual review": 0.45,
            "decline": 0.10,
        }
        base = m.get(s)
        if base is None:
            return None
        coeffs = _load_platt_coeffs()
        try:
            calibrated = _apply_platt(base, coeffs)
            return round(calibrated, 4)
        except Exception:
            return base

    # Estimate credit score from default probability when not provided
    est_credit = _clamp_credit_score(qse.credit_score)
    if est_credit is None and default_prob is not None:
        try:
            est_credit = _clamp_credit_score(850 - (float(default_prob) * 550.0))
        except Exception:
            est_credit = None

    scores = Scores(
        credit_score=est_credit,
        default_probability=default_prob,
        overall_risk_score=(default_prob * 100.0) if default_prob is not None else None,
        ensemble_confidence=None,
        approval_probability=_approval_probability_from(getattr(qaa, "final_recommendation", None)),
    )

    # Links section for UI deeplinks
    links = [
        {"rel": "Explainability", "href": "/ui/explainability", "title": "Explainability"},
        {"rel": "Compliance", "href": "/ui/compliance", "title": "Compliance Detail"},
    ]

    # Formal risk dimensions with weights and normalization
    aff = qse.affordability_and_obligations or {}
    bank = qse.bank_and_mobile_money_dynamics or {}
    core = qse.core_credit_performance or {}
    beh = qse.behavioral_intelligence or {}
    capacity = None
    try:
        buf = float(aff.get("affordability_buffer_ratio")) if aff.get("affordability_buffer_ratio") is not None else None
        res_ratio = float(aff.get("residual_income_ratio")) if aff.get("residual_income_ratio") is not None else None
        if buf is not None and res_ratio is not None:
            capacity = max(0.0, min(1.0, (1.0 - buf) * 0.6 + (1.0 - res_ratio) * 0.4))
    except Exception:
        capacity = None
    liquidity = None
    try:
        days = float(aff.get("cash_buffer_days")) if aff.get("cash_buffer_days") is not None else None
        overdraft = float(bank.get("overdraft_usage_days_90d")) if bank.get("overdraft_usage_days_90d") is not None else None
        if days is not None or overdraft is not None:
            # More days buffer => lower liquidity risk; more overdraft days => higher risk
            liquidity = None
            if days is not None:
                liquidity = max(0.0, min(1.0, 1.0 - min(days / 90.0, 1.0)))
            if overdraft is not None:
                overd = max(0.0, min(1.0, overdraft / 90.0))
                liquidity = (liquidity or 0.0) * 0.5 + overd * 0.5
    except Exception:
        liquidity = None
    credit_risk = None
    try:
        dti = float(aff.get("debt_to_income_ratio")) if aff.get("debt_to_income_ratio") is not None else None
        del30 = float(core.get("delinquency_30d_count_12m")) if core.get("delinquency_30d_count_12m") is not None else 0.0
        del60 = float(core.get("delinquency_60d_count_12m")) if core.get("delinquency_60d_count_12m") is not None else 0.0
        del90 = float(core.get("delinquency_90d_count_12m")) if core.get("delinquency_90d_count_12m") is not None else 0.0
        if dti is not None:
            # Normalize DTI to 0..1 using 0.6 as upper-risk bound
            dti_norm = max(0.0, min(1.0, dti / 0.6))
            delinquency_norm = max(0.0, min(1.0, (del30 + 2 * del60 + 3 * del90) / 10.0))
            credit_risk = round(min(1.0, dti_norm * 0.7 + delinquency_norm * 0.3), 4)
    except Exception:
        credit_risk = None
    character_risk = None
    try:
        # Aggregate available behavioral signals; if none, derive from explainability.
        signals = []
        for v in [
            (beh.get("behavioral_consistency_score") if beh.get("behavioral_consistency_score") is not None else None),
            (beh.get("conscientiousness_score") if beh.get("conscientiousness_score") is not None else None),
            (digital.get("digital_behavior_intelligence") if digital.get("digital_behavior_intelligence") is not None else None),
            (digital.get("savings_behavior_score") if digital.get("savings_behavior_score") is not None else None),
            (beh.get("payment_discipline_score") if beh.get("payment_discipline_score") is not None else None),
        ]:
            if isinstance(v, (int, float)):
                signals.append(float(v))
        char_base = None
        if signals:
            # Normalize to 0..100 baseline
            bounded = [max(0.0, min(100.0, s)) for s in signals]
            char_base = sum(bounded) / float(len(bounded))
        else:
            # Fallback from explainability feature importance if available
            try:
                fi = (expl.feature_importance or []) if expl else []
                weights = {
                    "conscientiousness_score": 1.0,
                    "behavioral_consistency_score": 1.0,
                    "digital_behavior_intelligence": 0.8,
                    "savings_behavior_score": 0.7,
                    "payment_discipline_score": 1.0,
                }
                acc = []
                for item in fi:
                    name = item.get("feature") or item.get("name")
                    imp = item.get("importance") if isinstance(item.get("importance"), (int, float)) else None
                    if name in weights and imp is not None:
                        # Map signed importance [-1..1] to an approximate 0..100 score around 50
                        approx = max(0.0, min(100.0, 50.0 + 50.0 * float(imp)))
                        acc.append(approx * weights[name])
                if acc:
                    char_base = sum(acc) / float(len(acc))
            except Exception:
                char_base = None
        if char_base is None:
            char_base = 55.0  # neutral baseline
        # Convert baseline to risk 0..1 (higher baseline -> lower risk)
        character_risk = round(max(0.0, min(1.0, 1.0 - (char_base / 100.0))), 4)
    except Exception:
        character_risk = None

    # Consolidate risk dimensions and attach to structured risk_analysis
    risk_dimensions = {
        "capacity_risk": capacity,
        "liquidity_risk": liquidity,
        "credit_risk": credit_risk,
        "character_risk": character_risk,
    }
    try:
        # Ensure we always return a structured risk_analysis with dimensions
        from .models import RiskDimensions as RiskDimensionsModel, RiskAnalysisExtended as RiskAnalysisExtendedModel
        if risk_ext is None:
            risk_ext = RiskAnalysisExtendedModel(
                overall_risk_score=(default_prob * 100.0) if default_prob is not None else None,
                risk_dimensions=RiskDimensionsModel(**risk_dimensions),
                risk_scenarios=[],
                risk_mitigation=[],
                risk_factors=[],
                protective_factors=[],
            )
        else:
            # Update existing risk_ext with computed dimensions
            risk_ext.risk_dimensions = RiskDimensionsModel(**risk_dimensions)
            if risk_ext.overall_risk_score is None and default_prob is not None:
                risk_ext.overall_risk_score = default_prob * 100.0
    except Exception:
        # If anything goes wrong, keep risk_ext as-is
        pass

    extended: dict = {
        "request_id": qse.request_id,
        "customer_id": qse.customer_id,
        "correlation_id": qse.correlation_id,
        "credit_score": _clamp_credit_score(qse.credit_score),
        "risk_level": effective_risk_level,
        "risk_category": risk_category,
        "default_probability": default_prob,
        "confidence_score": None,
        "model_type_used": None,
        "model_version": qse.model_version or governance.get("model_version"),
        "features_count": qse.features_count,
        "ethiopian_market_optimized": True,
        "feature_analysis": qse.feature_analysis,
        "explainability": expl.model_dump() if expl else None,
        "risk_analysis": risk_ext.model_dump() if risk_ext else None,
        # Ensemble details: base Gemini scoring; optional multi-model reflection via env
        "ensemble_details": {
            "features_analyzed": qse.features_count,
            "ensemble_confidence": governance.get("model_confidence_score"),
            "diversity_index": 0.0,
            "stability_metric": 0.9,
            "individual_predictions": {
                "gemini": _apply_platt(default_prob if default_prob is not None else (scores.approval_probability or 0.5), _load_platt_coeffs()),
            },
            "weights": {"gemini": 1.0},
            "feature_categories": {
                "affordability": len((qse.affordability_and_obligations or {})),
                "credit": len((qse.core_credit_performance or {})),
                "behavioral": len((qse.behavioral_intelligence or {})),
            },
            "provenance_run_ids": {
                "gemini": os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash"),
            },
        },
        "nbe_compliance_status": qse.nbe_compliance_status.model_dump() if qse.nbe_compliance_status else None,
        "nbe_compliance": None,
        "processing_metadata": ProcessingMetadata(
            timestamp=governance.get("timestamp"),
            processing_time_ms=None,
            data_quality_score=governance.get("data_quality_score"),
            feature_completeness=None,
        ).model_dump(),
        "processing_time_ms": None,
        "timestamp": None,
        "additional_insights": qse.additional_insights.model_dump() if qse.additional_insights else None,
        "qaa_report": qaa.model_dump(),
        "scores": scores.model_dump(),
        "links": links,
    }

    # Compute consensus score from individual predictions and weights if not provided
    try:
        ed = extended["ensemble_details"]
        # Optional multi-model ensemble mode
        if settings.ENSEMBLE_MODE.lower() == "multi" and settings.ENSEMBLE_EXTRA_MODELS:
            preds = ed.get("individual_predictions") or {}
            gem = preds.get("gemini", 0.0)
            extra_weight = round(1.0 / (len(settings.ENSEMBLE_EXTRA_MODELS) + 1), 4)
            ed.setdefault("weights", {})["gemini"] = extra_weight
            ed.setdefault("provenance_run_ids", {})
            for mdl in settings.ENSEMBLE_EXTRA_MODELS:
                preds[mdl] = gem
                ed["weights"][mdl] = extra_weight
                ed["provenance_run_ids"][mdl] = f"configured:{mdl}"
            ed["individual_predictions"] = preds
        preds = ed.get("individual_predictions") or {}
        wts = ed.get("weights") or {}
        total_w = sum(wts.values()) or 1.0
        cons = sum((preds.get(k, 0.0) * wts.get(k, 0.0)) for k in wts.keys()) / total_w
        ed["consensus_score"] = round(cons, 4)
        # simple diversity as std dev
        import statistics
        if len(preds.values()) >= 2:
            ed["diversity_index"] = round(statistics.pstdev(list(preds.values())), 4)
    except Exception:
        pass

    extended_model = QAAExtendedResponse(**extended)

    # Audit completed
    try:
        # Compute processing time
        end_ms = int(time.time() * 1000)
        extended_model.processing_time_ms = end_ms - start_ms
        if extended_model.processing_metadata:
            extended_model.processing_metadata.processing_time_ms = extended_model.processing_time_ms
        await audit_completed(analysis_id, extended_model.model_dump())
    except Exception as e:
        logger.warning(f"Audit complete failed: {e}")
    # Metrics and structured log
    try:
        PROC_TIME_SEC.observe(extended_model.processing_time_ms / 1000.0 if extended_model.processing_time_ms else 0.0)
        REQ_COUNTER.labels(status="success").inc()
    except Exception:
        pass
    logger.info(json.dumps({
        "event": "analyze_complete",
        "analysis_id": analysis_id,
        "correlation_id": correlation_id,
        "processing_time_ms": extended_model.processing_time_ms,
    }))
    return extended_model


@app.get("/v1/analyze/{analysis_id}", tags=["Analysis"], summary="Retrieve a stored analysis")
async def get_analysis_by_id(analysis_id: str):
    try:
        stored = await get_analysis(analysis_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lookup error: {e}")
    if not stored:
        raise HTTPException(status_code=404, detail="Analysis not found or auditing disabled")
    return stored


@app.post("/v1/analyze/async", tags=["Analysis"], summary="Submit analysis job asynchronously")
async def analyze_async(
    request: Request,
    qse: QSEReportInput,
    x_correlation_id: str | None = Header(None),
):
    job_id = str(uuid.uuid4())
    correlation_id = x_correlation_id or request.headers.get("X-Correlation-ID")
    try:
        await audit_created(job_id, correlation_id or job_id, {"async": True})
    except Exception:
        pass
    # In a real system, enqueue the job. Here, return the tracking payload.
    return {"job_id": job_id, "status": "queued"}


@app.get("/v1/jobs/{job_id}", tags=["Analysis"], summary="Poll an async job status")
async def get_job_status(job_id: str):
    # Placeholder: normally check a job store
    return {"job_id": job_id, "status": "pending"}


@app.get("/v1/models", tags=["Explainability"], summary="List active model version and health")
async def list_models():
    # Basic transparency route; can be expanded to reflect real model discovery
    active_model = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash")
    return {
        "active_model": active_model,
        "last_refresh": None,
        "health": "ok",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=7000, reload=True)


@app.on_event("startup")
async def _startup():
    # Initialize DB if configured — do not block app startup on DB failures
    try:
        await init_db()
    except Exception as e:
        logger.warning(f"DB init failed; auditing disabled: {e}")

    # Prometheus metrics already configured at import-time