# Gateway Assessment Endpoint

## Overview

The `/v1/analyze/gateway` endpoint accepts API Gateway assessment results and returns comprehensive analysis with **Scores**, **Analysis Results**, **Decisions**, and **Recommendations**.

## Endpoint

**POST** `/v1/analyze/gateway`

## Request Format

The endpoint accepts a `GatewayAssessmentInput` JSON payload containing:

- Credit scores and components
- Fraud detection results
- Risk analysis and breakdown
- Default predictions
- Ability/Willingness to pay scores
- NBE compliance status
- Product recommendations and pricing
- Feature completeness
- Tier availability

See `examples/gateway_assessment_sample.json` for a complete example.

## Response Format

The response contains four main sections:

### 1. Scores

Consolidated scores from all assessment components:

```json
{
  "scores": {
    "credit_score": 600.0,
    "credit_score_components": {
      "traditional_score": 570.0,
      "alternative_score": 630.0,
      "ensemble_score": 600.0
    },
    "fraud_score": 0.0,
    "default_probability": 0.2,
    "risk_scores": {
      "credit_risk": 0.0,
      "capacity_risk": 0.0,
      "liquidity_risk": 0.0,
      "character_risk": 0.0
    },
    "ability_to_pay_score": 35.0,
    "willingness_to_pay_score": 67.0,
    "overall_risk_score": 0.0
  }
}
```

### 2. Analysis

Detailed analysis breakdown:

```json
{
  "analysis": {
    "risk_analysis": {
      "overall_risk_score": 0.0,
      "risk_level": "LOW",
      "risk_breakdown": {...},
      "critical_risk_factors": [],
      "confidence_score": 0.788
    },
    "fraud_analysis": {
      "fraud_score": 0.0,
      "fraud_risk_level": "minimal",
      "fraud_signals": [],
      "block_transaction": false
    },
    "credit_analysis": {...},
    "compliance_analysis": {...},
    "product_analysis": {...},
    "feature_analysis": {...}
  }
}
```

### 3. Decisions

Final decisions and approval status:

```json
{
  "decisions": {
    "final_decision": "requires_review",
    "approval_status": "requires_review",
    "decision_reason": "All risk factors within acceptable range",
    "fraud_decision": {
      "block_transaction": false,
      "require_manual_review": false,
      "recommendation": "APPROVE - No significant fraud indicators"
    },
    "risk_decision": {
      "risk_level": "LOW",
      "decision": "approve"
    },
    "compliance_decision": {
      "compliant": true,
      "overall_compliance": "pass"
    }
  }
}
```

### 4. Recommendations

Actionable recommendations based on assessment:

```json
{
  "recommendations": [
    "Proceed with standard approval process",
    "Regular monitoring schedule",
    "Provide mobile money history and utility bills for better assessment",
    "Ability to pay score is low (35) - consider lower loan amount or longer term",
    "Recommended product: Personal Loan (Amount: 71,928 ETB, Suitability: 65%)"
  ]
}
```

## Decision Logic

The endpoint determines final decisions based on:

1. **Fraud Detection**: If `block_transaction` is true → Decline
2. **Manual Review Required**: If fraud requires manual review → Pending Review
3. **NBE Compliance**: If compliance fails → Decline
4. **Risk Level**: 
   - LOW → Approve
   - MEDIUM → Approve with Conditions
   - HIGH → Requires Review
5. **Gateway Input**: Uses `final_decision` and `approval_status` if provided

## Recommendations Generated

The endpoint generates recommendations from:

- Risk analysis recommendations
- Fraud detection signals
- Feature completeness gaps
- Tier improvement suggestions
- Product recommendations (best eligible product)
- ATP/WTP score thresholds
- Default probability warnings
- NBE compliance issues

## Example Usage

```bash
curl -X POST http://localhost:5002/v1/analyze/gateway \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: corr-123" \
  --data @examples/gateway_assessment_sample.json
```

## Response Status Codes

- **200**: Success - Analysis completed
- **422**: Validation error - Invalid input format
- **500**: Internal server error

## Testing

Run the test script:

```bash
bash test_gateway_endpoint.sh
```

## Differences from `/v1/analyze`

- **Input Format**: Gateway assessment format (already processed) vs QSE raw format
- **Output Format**: Structured scores/analysis/decisions/recommendations vs Extended QAA response
- **Processing**: Direct analysis of assessment results vs Qualitative synthesis from QSE data
- **Use Case**: API Gateway orchestration results vs Direct QSE integration

Both endpoints are available and serve different use cases.

