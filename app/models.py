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

    # UX tailoring
    locale: Optional[str] = Field(None, description="BCP 47 tag like 'en', 'am', 'en-US'")
    output_style: Optional[Literal["short", "standard", "detailed"]] = Field(
        None, description="Controls verbosity of qualitative text output"
    )

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


class Scores(BaseModel):
    credit_score: Optional[int] = Field(None, ge=300, le=850, description="Credit score between 300 and 850")
    default_probability: Optional[float] = None
    overall_risk_score: Optional[float] = None
    ensemble_confidence: Optional[float] = None
    approval_probability: Optional[float] = None


class ShapGlobalImportanceEntry(BaseModel):
    feature: str
    importance: float


class FeatureImpactEntry(BaseModel):
    feature: str
    importance: float
    impact: Literal["positive", "neutral", "negative"]


class ShapAnalysisExtended(BaseModel):
    global_importance: List[ShapGlobalImportanceEntry] = []
    local_explanation: Optional[str] = None
    description: Optional[str] = None
    confidence_factors: List[str] = []
    risk_factors: List[str] = []


class ExplainabilityExtended(BaseModel):
    shap_analysis: Optional[ShapAnalysisExtended] = None
    feature_importance: List[FeatureImpactEntry] = []
    explanation_available: Optional[bool] = None
    interpretation: Optional[str] = None


class RiskDimensions(BaseModel):
    credit_risk: Optional[float] = None
    liquidity_risk: Optional[float] = None
    capacity_risk: Optional[float] = None
    character_risk: Optional[float] = None
    financial_risk: Optional[float] = None
    behavioral_risk: Optional[float] = None
    market_risk: Optional[float] = None
    operational_risk: Optional[float] = None


class RiskScenarioExtended(BaseModel):
    scenario: str
    probability: Optional[float] = None
    description: Optional[str] = None
    expected_default_rate: Optional[float] = None
    impact: Literal["low", "medium", "high"]


class RiskMitigationItem(BaseModel):
    category: str
    recommendation: str
    priority: Literal["low", "medium", "high"]


class RiskAnalysisExtended(BaseModel):
    overall_risk_score: Optional[float] = None
    risk_dimensions: Optional[RiskDimensions] = None
    risk_scenarios: List[RiskScenarioExtended] = []
    risk_mitigation: List[RiskMitigationItem] = []
    risk_factors: List[str] = []
    protective_factors: List[str] = []


class EnsembleDetails(BaseModel):
    features_analyzed: Optional[int] = None
    feature_categories: Optional[Dict[str, int]] = None
    ensemble_confidence: Optional[float] = None
    individual_predictions: Optional[Dict[str, float]] = None
    weights: Optional[Dict[str, float]] = None
    consensus_score: Optional[float] = None
    diversity_index: Optional[float] = None
    stability_metric: Optional[float] = None
    provenance_run_ids: Optional[Dict[str, str]] = None


class NBEComplianceStatusExtended(BaseModel):
    overall_compliant: Optional[bool] = None
    compliance_score: Optional[int] = None
    salary_rule_compliant: Optional[bool] = None
    amount_rule_compliant: Optional[bool] = None
    interest_rate_compliant: Optional[bool] = None
    recommended_interest_rate: Optional[float] = None
    max_affordable_payment_etb: Optional[float] = None
    proposed_payment_etb: Optional[float] = None
    compliance_details: Optional[Dict[str, str]] = None
    recommendations: List[str] = []
    regulatory_notes: List[str] = []


class ProcessingMetadata(BaseModel):
    timestamp: Optional[str] = None
    processing_time_ms: Optional[int] = None
    data_quality_score: Optional[float] = None
    feature_completeness: Optional[float] = None


class LendingRecommendations(BaseModel):
    recommended_loan_amount: Optional[float] = None
    suggested_interest_rate: Optional[float] = None
    repayment_period_months: Optional[int] = None
    collateral_requirement: Optional[str] = None
    approval_probability: Optional[float] = None


class ModelPerformance(BaseModel):
    accuracy: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1_score: Optional[float] = None
    auc_roc: Optional[float] = None
    calibration_score: Optional[float] = None
    feature_stability: Optional[float] = None
    prediction_consistency: Optional[float] = None


class AdditionalInsightsExtended(BaseModel):
    market_context: Optional[Dict[str, Any]] = None
    lending_recommendations: Optional[LendingRecommendations] = None
    model_performance: Optional[ModelPerformance] = None


class LinkItem(BaseModel):
    rel: str
    href: str
    title: Optional[str] = None


class QAAExtendedResponse(BaseModel):
    """Extended response combining core QAA qualitative report with structured fields
    similar to sample_response.json for richer downstream consumption.

    Most nested sections are modeled as generic objects to allow flexibility while
    preserving the overall shape used in the sample response.
    """

    # Core identifiers and summary from QSE
    request_id: str
    customer_id: str
    correlation_id: Optional[str] = None

    credit_score: Optional[float] = None
    risk_level: Optional[str] = None
    risk_category: Optional[str] = None
    default_probability: Optional[float] = None
    confidence_score: Optional[float] = None
    model_type_used: Optional[str] = None
    model_version: Optional[str] = None
    features_count: Optional[int] = None
    ethiopian_market_optimized: Optional[bool] = None

    # Rich sections (kept flexible)
    feature_analysis: Optional[Dict[str, Any]] = None
    explainability: Optional[ExplainabilityExtended] = None
    risk_analysis: Optional[RiskAnalysisExtended] = None
    ensemble_details: Optional[EnsembleDetails] = None
    nbe_compliance_status: Optional[NBEComplianceStatusExtended] = None
    nbe_compliance: Optional[Dict[str, Any]] = None
    processing_metadata: Optional[ProcessingMetadata] = None
    processing_time_ms: Optional[int] = None
    timestamp: Optional[str] = None
    additional_insights: Optional[AdditionalInsightsExtended] = None

    # Include the original qualitative report so existing consumers have access
    qaa_report: QAAQualitativeReport

    # Consolidated scores
    scores: Optional[Scores] = None

    # UI deep-links
    links: Optional[List[LinkItem]] = None

    class Config:
        extra = "ignore"


class QAAExtendedResponseV1_1(QAAExtendedResponse):
    """Version 1.1: adds required links field for UI deep-links and
    future backward-compatible additions."""

    links: List[LinkItem]