"""
Gateway Assessment Analyzer - Processes API Gateway assessment results
and generates comprehensive analysis with scores, decisions, and recommendations.
"""
import uuid
from typing import Dict, Any, List
from datetime import datetime

from .models_extended import GatewayAssessmentInput, EnhancedAnalysisResponse


def analyze_gateway_assessment(gateway_input: GatewayAssessmentInput, analysis_id: str) -> EnhancedAnalysisResponse:
    """
    Analyze gateway assessment input and generate comprehensive response with:
    - Scores (credit, fraud, risk, ATP/WTP)
    - Analysis results (detailed breakdown)
    - Decisions (final decision and approval status)
    - Recommendations (actionable recommendations)
    """
    
    # Extract and consolidate scores
    scores = _extract_scores(gateway_input)
    
    # Generate detailed analysis
    analysis = _generate_analysis(gateway_input)
    
    # Determine decisions
    decisions = _determine_decisions(gateway_input)
    
    # Generate recommendations
    recommendations = _generate_recommendations(gateway_input)
    
    return EnhancedAnalysisResponse(
        request_id=gateway_input.request_id,
        customer_id=gateway_input.customer_id,
        correlation_id=gateway_input.correlation_id or analysis_id,
        assessment_id=gateway_input.assessment_id or analysis_id,
        scores=scores,
        analysis=analysis,
        decisions=decisions,
        recommendations=recommendations,
        qualitative_report=None,  # Can be added if needed
        processing_time_ms=None,
        timestamp=datetime.utcnow().isoformat() + "Z",
    )


def _extract_scores(gateway_input: GatewayAssessmentInput) -> Dict[str, Any]:
    """Extract and consolidate all scores from gateway input."""
    scores = {
        "credit_score": gateway_input.credit_score,
        "credit_score_components": {},
        "fraud_score": gateway_input.fraud_score or 0.0,
        "default_probability": gateway_input.default_probability or 0.0,
        "risk_scores": {},
        "ability_to_pay_score": gateway_input.ability_to_pay_score,
        "willingness_to_pay_score": gateway_input.willingness_to_pay_score,
        "combined_atp_wtp_score": gateway_input.combined_atp_wtp_score,
    }
    
    # Credit score components
    if gateway_input.credit_score_components:
        scores["credit_score_components"] = {
            "traditional_score": gateway_input.credit_score_components.traditional_score,
            "alternative_score": gateway_input.credit_score_components.alternative_score,
            "realtime_score": gateway_input.credit_score_components.realtime_score,
            "ensemble_score": gateway_input.credit_score_components.ensemble_score,
        }
    
    # Risk scores
    if gateway_input.risk_breakdown:
        scores["risk_scores"] = {
            "credit_risk": gateway_input.risk_breakdown.credit_risk,
            "capacity_risk": gateway_input.risk_breakdown.capacity_risk,
            "liquidity_risk": gateway_input.risk_breakdown.liquidity_risk,
            "character_risk": gateway_input.risk_breakdown.character_risk,
        }
    
    if gateway_input.overall_risk_score is not None:
        scores["overall_risk_score"] = gateway_input.overall_risk_score
    
    # Default prediction confidence
    if gateway_input.default_prediction:
        scores["default_prediction_confidence"] = gateway_input.default_prediction.confidence_score
    
    # ATP/WTP analysis
    if gateway_input.atp_wtp_analysis:
        scores["atp_wtp_analysis"] = {
            "score": gateway_input.atp_wtp_analysis.score,
            "confidence": gateway_input.atp_wtp_analysis.confidence,
            "assessment": gateway_input.atp_wtp_analysis.assessment,
        }
    
    return scores


def _generate_analysis(gateway_input: GatewayAssessmentInput) -> Dict[str, Any]:
    """Generate detailed analysis breakdown."""
    analysis = {
        "risk_analysis": {},
        "fraud_analysis": {},
        "credit_analysis": {},
        "compliance_analysis": {},
        "product_analysis": {},
        "feature_analysis": {},
    }
    
    # Risk analysis
    if gateway_input.risk_analysis:
        analysis["risk_analysis"] = {
            "overall_risk_score": gateway_input.risk_analysis.overall_risk_score,
            "risk_level": gateway_input.risk_analysis.risk_level,
            "risk_breakdown": gateway_input.risk_analysis.risk_breakdown.model_dump() if gateway_input.risk_analysis.risk_breakdown else {},
            "critical_risk_factors": gateway_input.risk_analysis.critical_risk_factors,
            "confidence_score": gateway_input.risk_analysis.confidence_score,
        }
    
    # Fraud analysis
    if gateway_input.fraud_detection_result:
        analysis["fraud_analysis"] = {
            "fraud_score": gateway_input.fraud_detection_result.fraud_score,
            "fraud_risk_level": gateway_input.fraud_detection_result.fraud_risk_level,
            "fraud_signals": gateway_input.fraud_detection_result.fraud_signals,
            "fraud_signals_count": gateway_input.fraud_detection_result.fraud_signals_count,
            "block_transaction": gateway_input.fraud_detection_result.block_transaction,
            "require_manual_review": gateway_input.fraud_detection_result.require_manual_review,
        }
    
    # Credit analysis
    analysis["credit_analysis"] = {
        "credit_score": gateway_input.credit_score,
        "risk_level": gateway_input.risk_level,
        "risk_category": gateway_input.risk_category,
        "model_version": gateway_input.model_version,
        "model_type_used": gateway_input.model_type_used,
    }
    
    # Default prediction
    if gateway_input.default_prediction:
        analysis["default_prediction"] = {
            "default_probability": gateway_input.default_prediction.default_probability,
            "risk_level": gateway_input.default_prediction.risk_level,
            "time_to_default_months": gateway_input.default_prediction.time_to_default_months,
            "confidence_score": gateway_input.default_prediction.confidence_score,
        }
    
    # Compliance analysis
    if gateway_input.nbe_compliance_status:
        analysis["compliance_analysis"] = {
            "overall_compliance": gateway_input.nbe_compliance_status.overall_compliance,
            "one_third_rule": gateway_input.nbe_compliance_status.one_third_rule,
            "one_third_rule_details": gateway_input.nbe_compliance_status.one_third_rule_details,
            "interest_rate_range": gateway_input.nbe_compliance_status.interest_rate_range,
            "loan_amount_limits": gateway_input.nbe_compliance_status.loan_amount_limits,
        }
    
    # Product analysis
    if gateway_input.product_recommendations:
        analysis["product_analysis"] = {
            "recommendations": [rec.model_dump() for rec in gateway_input.product_recommendations],
            "limits": {k: v.model_dump() for k, v in gateway_input.product_limits.items()},
            "pricing": {k: v.model_dump() for k, v in gateway_input.product_pricing.items()},
        }
    
    # Feature completeness
    if gateway_input.feature_completeness:
        analysis["feature_analysis"] = {
            "completeness": gateway_input.feature_completeness.completeness,
            "meets_threshold": gateway_input.feature_completeness.meets_threshold,
            "missing_features": gateway_input.feature_completeness.missing_features,
            "default_features": gateway_input.feature_completeness.default_features,
        }
    
    # Explainability
    if gateway_input.explainability:
        analysis["explainability"] = gateway_input.explainability
    
    if gateway_input.reason_codes:
        analysis["reason_codes"] = gateway_input.reason_codes
    
    return analysis


def _determine_decisions(gateway_input: GatewayAssessmentInput) -> Dict[str, Any]:
    """Determine final decisions based on gateway input."""
    decisions = {
        "final_decision": gateway_input.final_decision or "requires_review",
        "approval_status": gateway_input.approval_status or "requires_review",
        "decision_reason": gateway_input.decision_reason or "Assessment completed",
        "fraud_decision": {},
        "risk_decision": {},
        "compliance_decision": {},
    }
    
    # Fraud decision
    if gateway_input.fraud_detection_result:
        decisions["fraud_decision"] = {
            "block_transaction": gateway_input.fraud_detection_result.block_transaction,
            "require_manual_review": gateway_input.fraud_detection_result.require_manual_review,
            "recommendation": gateway_input.fraud_detection_result.recommendation,
        }
    
    # Risk decision
    if gateway_input.risk_analysis:
        risk_level = gateway_input.risk_analysis.risk_level.upper()
        if risk_level in ["LOW", "LOW RISK"]:
            risk_decision = "approve"
        elif risk_level in ["MEDIUM", "MEDIUM RISK"]:
            risk_decision = "approve_with_conditions"
        else:
            risk_decision = "requires_review"
        
        decisions["risk_decision"] = {
            "risk_level": gateway_input.risk_analysis.risk_level,
            "overall_risk_score": gateway_input.risk_analysis.overall_risk_score,
            "decision": risk_decision,
        }
    
    # Compliance decision
    if gateway_input.nbe_compliance_status:
        compliance_status = gateway_input.nbe_compliance_status.overall_compliance.lower()
        decisions["compliance_decision"] = {
            "compliant": compliance_status == "pass",
            "overall_compliance": gateway_input.nbe_compliance_status.overall_compliance,
            "one_third_rule": gateway_input.nbe_compliance_status.one_third_rule,
        }
    
    # Overall decision logic
    if gateway_input.fraud_detection_result and gateway_input.fraud_detection_result.block_transaction:
        decisions["final_decision"] = "decline"
        decisions["approval_status"] = "declined"
        decisions["decision_reason"] = "Transaction blocked due to fraud indicators"
    elif gateway_input.fraud_detection_result and gateway_input.fraud_detection_result.require_manual_review:
        decisions["final_decision"] = "requires_review"
        decisions["approval_status"] = "pending_manual_review"
    elif gateway_input.nbe_compliance_status and gateway_input.nbe_compliance_status.overall_compliance.lower() != "pass":
        decisions["final_decision"] = "decline"
        decisions["approval_status"] = "declined"
        decisions["decision_reason"] = "NBE compliance requirements not met"
    elif gateway_input.final_decision:
        decisions["final_decision"] = gateway_input.final_decision
        decisions["approval_status"] = gateway_input.approval_status or gateway_input.final_decision
    
    return decisions


def _generate_recommendations(gateway_input: GatewayAssessmentInput) -> List[str]:
    """Generate actionable recommendations based on assessment."""
    recommendations = []
    
    # Risk recommendations
    if gateway_input.risk_recommendations:
        recommendations.extend(gateway_input.risk_recommendations)
    
    if gateway_input.risk_analysis and gateway_input.risk_analysis.recommendations:
        recommendations.extend(gateway_input.risk_analysis.recommendations)
    
    # Fraud recommendations
    if gateway_input.fraud_detection_result:
        if gateway_input.fraud_detection_result.require_manual_review:
            recommendations.append("Manual review required due to fraud risk indicators")
        elif gateway_input.fraud_detection_result.fraud_signals_count > 0:
            recommendations.append(f"Monitor {gateway_input.fraud_detection_result.fraud_signals_count} fraud signal(s)")
    
    # Feature completeness recommendations
    if gateway_input.feature_completeness and gateway_input.feature_completeness.recommendations:
        recommendations.extend(gateway_input.feature_completeness.recommendations)
    
    # Tier improvement recommendations
    if gateway_input.tier_improvement_recommendations:
        recommendations.extend(gateway_input.tier_improvement_recommendations)
    
    # Product recommendations
    if gateway_input.product_recommendations:
        eligible_products = [p for p in gateway_input.product_recommendations if p.eligible]
        if eligible_products:
            best_product = max(eligible_products, key=lambda p: p.suitability_score)
            recommendations.append(
                f"Recommended product: {best_product.product_type} "
                f"(Amount: {best_product.recommended_amount:,.0f} ETB, "
                f"Suitability: {best_product.suitability_score}%)"
            )
    
    # ATP/WTP recommendations
    if gateway_input.ability_to_pay_score is not None and gateway_input.ability_to_pay_score < 50:
        recommendations.append(f"Ability to pay score is low ({gateway_input.ability_to_pay_score}) - consider lower loan amount or longer term")
    
    if gateway_input.willingness_to_pay_score is not None and gateway_input.willingness_to_pay_score < 50:
        recommendations.append(f"Willingness to pay score is low ({gateway_input.willingness_to_pay_score}) - additional verification recommended")
    
    # Default probability recommendations
    if gateway_input.default_probability and gateway_input.default_probability > 0.25:
        recommendations.append("High default probability - consider risk mitigation measures")
    elif gateway_input.default_probability and gateway_input.default_probability > 0.15:
        recommendations.append("Moderate default probability - enhanced monitoring recommended")
    
    # Compliance recommendations
    if gateway_input.nbe_compliance_status:
        if gateway_input.nbe_compliance_status.one_third_rule.lower() != "pass":
            recommendations.append("One-third rule compliance issue - adjust loan amount or terms")
    
    # Remove duplicates and return
    return list(dict.fromkeys(recommendations))  # Preserves order while removing duplicates

