from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field


class CreditScoreComponents(BaseModel):
    traditional_score: Optional[float] = None
    alternative_score: Optional[float] = None
    realtime_score: Optional[float] = None
    ensemble_score: Optional[float] = None


class FraudDetectionResult(BaseModel):
    fraud_score: float
    fraud_risk_level: str
    fraud_signals: List[str] = []
    fraud_signals_count: int = 0
    recommendation: str
    block_transaction: bool = False
    require_manual_review: bool = False


class DefaultPrediction(BaseModel):
    default_probability: float
    risk_level: str
    survival_probabilities: List[float] = []
    hazard_ratios: List[float] = []
    time_to_default_months: Optional[float] = None
    confidence_score: float = 0.0


class RiskBreakdown(BaseModel):
    credit_risk: float = 0.0
    capacity_risk: float = 0.0
    liquidity_risk: float = 0.0
    character_risk: float = 0.0


class RiskAnalysisExtended(BaseModel):
    overall_risk_score: float = 0.0
    risk_level: str
    risk_breakdown: RiskBreakdown
    critical_risk_factors: List[str] = []
    confidence_score: float = 0.0
    recommendations: List[str] = []


class ATPWTPAnalysis(BaseModel):
    score: float
    factors: List[str] = []
    confidence: float = 0.0
    assessment: str


class FeatureCompleteness(BaseModel):
    is_valid: bool
    completeness: Dict[str, Any]
    min_completeness_required: float
    meets_threshold: bool
    missing_features: List[str] = []
    default_features: List[str] = []
    recommendations: List[str] = []


class NBEComplianceDetails(BaseModel):
    one_third_rule: str
    one_third_rule_details: Dict[str, Any]
    interest_rate_range: Dict[str, float]
    loan_amount_limits: Dict[str, float]
    overall_compliance: str
    # Note: 'status' field is not in the actual input, using overall_compliance instead
    
    class Config:
        extra = "ignore"  # Ignore any extra fields like 'status' if present


class ProductRecommendation(BaseModel):
    product_type: str
    product_key: str
    eligible: bool
    credit_score: float
    risk_level: str
    max_amount: float
    recommended_amount: float
    suitability_score: float
    key_benefits: List[str] = []
    product_specific_data: Dict[str, Any] = {}


class ProductLimit(BaseModel):
    product_type: str
    customer_id: str
    max_amount: float
    recommended_amount: float
    min_amount: float
    calculation_breakdown: Dict[str, Any]
    atp_score_used: Optional[float] = None
    wtp_score_used: Optional[float] = None
    timestamp: str


class ProductPricing(BaseModel):
    interest_rate: float
    apr: float
    monthly_payment: float
    total_repayment: float
    pricing_tier: str
    nbe_compliant: bool
    pricing_details: Dict[str, Any]
    valid_until: Optional[str] = None


class GatewayAssessmentInput(BaseModel):
    """Input format from API Gateway/Orchestration Service"""
    success: bool
    customer_id: str
    request_id: str
    correlation_id: Optional[str] = None
    assessment_timestamp: Optional[str] = None
    credit_score: Optional[float] = None
    credit_score_components: Optional[CreditScoreComponents] = None
    risk_level: Optional[str] = None
    risk_category: Optional[str] = None
    model_version: Optional[str] = None
    model_type_used: Optional[str] = None
    fraud_score: Optional[float] = None
    fraud_detection_result: Optional[FraudDetectionResult] = None
    fraud_risk_level: Optional[str] = None
    fraud_signals: List[str] = []
    fraud_block_transaction: bool = False
    default_probability: Optional[float] = None
    default_prediction: Optional[DefaultPrediction] = None
    survival_probabilities: List[float] = []
    hazard_ratios: List[float] = []
    time_to_default_months: Optional[float] = None
    risk_analysis: Optional[RiskAnalysisExtended] = None
    overall_risk_score: Optional[float] = None
    risk_breakdown: Optional[RiskBreakdown] = None
    critical_risk_factors: List[str] = []
    risk_recommendations: List[str] = []
    ability_to_pay_score: Optional[float] = None
    willingness_to_pay_score: Optional[float] = None
    combined_atp_wtp_score: Optional[float] = None
    atp_wtp_analysis: Optional[ATPWTPAnalysis] = None
    explainability: Dict[str, Any] = {}
    reason_codes: List[str] = []
    feature_importance: Dict[str, Any] = {}
    feature_completeness: Optional[FeatureCompleteness] = None
    nbe_compliance_status: Optional[NBEComplianceDetails] = None
    market_context: Dict[str, Any] = {}
    product_recommendations: List[ProductRecommendation] = []
    product_limits: Dict[str, ProductLimit] = {}
    product_pricing: Dict[str, ProductPricing] = {}
    final_decision: Optional[str] = None
    decision_reason: Optional[str] = None
    approval_status: Optional[str] = None
    processing_time_ms: Optional[int] = None
    services_called: List[str] = []
    assessment_id: Optional[str] = None
    error_details: Dict[str, Any] = {}
    tier_availability: Dict[str, bool] = {}
    tier_improvement_recommendations: List[str] = []

    class Config:
        extra = "ignore"


class AnalysisResult(BaseModel):
    """Structured analysis result"""
    scores: Dict[str, Any] = Field(..., description="All relevant scores")
    analysis: Dict[str, Any] = Field(..., description="Detailed analysis breakdown")
    decisions: Dict[str, Any] = Field(..., description="Final decisions and status")
    recommendations: List[str] = Field(..., description="Actionable recommendations")


class EnhancedAnalysisResponse(BaseModel):
    """Enhanced response with scores, analysis, decisions, and recommendations"""
    request_id: str
    customer_id: str
    correlation_id: Optional[str] = None
    assessment_id: Optional[str] = None
    
    # Scores section
    scores: Dict[str, Any] = Field(..., description="All scores (credit, fraud, risk, ATP/WTP)")
    
    # Analysis section
    analysis: Dict[str, Any] = Field(..., description="Detailed analysis results")
    
    # Decisions section
    decisions: Dict[str, Any] = Field(..., description="Final decisions and approval status")
    
    # Recommendations section
    recommendations: List[str] = Field(..., description="Actionable recommendations")
    
    # Qualitative report (from QAA)
    qualitative_report: Optional[Dict[str, Any]] = None
    
    # Processing metadata
    processing_time_ms: Optional[int] = None
    timestamp: Optional[str] = None

