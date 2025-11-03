from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field


class ShapFactor(BaseModel):
    name: str
    impact: float
    direction: Literal["positive", "negative"]


class ShapAnalysis(BaseModel):
    risk_factors: List[ShapFactor] = []
    confidence_factors: List[ShapFactor] = []
    global_importance_order: Optional[List[str]] = None


class RiskScenario(BaseModel):
    name: str
    description: str
    severity: Literal["Low", "Medium", "High"]


class RiskAnalysis(BaseModel):
    scenarios: List[RiskScenario] = []
    default_probability: Optional[float] = None


class NBECompliance(BaseModel):
    status: Literal["COMPLIANT", "NON_COMPLIANT"]
    reasons: List[str] = []


class AdditionalInsights(BaseModel):
    notes: Optional[str] = None
    tags: List[str] = []


class QSEReportInput(BaseModel):
    # Identifiers
    request_id: str
    customer_id: str
    correlation_id: Optional[str] = None

    # Optional governance fields if provided by QSE
    credit_score: Optional[float] = None
    risk_level: Optional[str] = None
    default_probability: Optional[float] = None
    model_version: Optional[str] = None
    features_count: Optional[int] = None

    # Match provided sample_request top-level sections
    core_credit_performance: Optional[Dict[str, Any]] = None
    affordability_and_obligations: Optional[Dict[str, Any]] = None
    bank_and_mobile_money_dynamics: Optional[Dict[str, Any]] = None
    identity_and_fraud_intelligence: Optional[Dict[str, Any]] = None
    personal_and_professional_stability: Optional[Dict[str, Any]] = None
    contextual_and_macroeconomic_factors: Optional[Dict[str, Any]] = None
    product_specific_intelligence: Optional[Dict[str, Any]] = None
    business_and_receivables_finance: Optional[Dict[str, Any]] = None
    behavioral_intelligence: Optional[Dict[str, Any]] = None
    model_governance_and_monitoring: Optional[Dict[str, Any]] = None
    loan_details: Optional[Dict[str, Any]] = None
    additional_context: Optional[Dict[str, Any]] = None
    digital_behavioral_intelligence: Optional[Dict[str, Any]] = None

    # Optional advanced sections (if QSE supplies them)
    feature_analysis: Optional[Dict[str, Any]] = None
    explainability: Optional[ShapAnalysis] = None
    risk_analysis: Optional[RiskAnalysis] = None
    nbe_compliance_status: Optional[NBECompliance] = None
    additional_insights: Optional[AdditionalInsights] = None

    class Config:
        extra = "ignore"


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