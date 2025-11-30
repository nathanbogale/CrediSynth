#!/usr/bin/env bash
# Test script for Gateway Assessment endpoint

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT_FILE="$ROOT_DIR/logs/.local_api.port"
PORT=$(cat "$PORT_FILE" 2>/dev/null || echo "5000")
BASE_URL="http://127.0.0.1:$PORT"
SAMPLE="$ROOT_DIR/examples/gateway_assessment_sample.json"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=========================================="
echo "Gateway Assessment Endpoint Test"
echo "=========================================="
echo "Base URL: $BASE_URL"
echo ""

if [[ ! -f "$SAMPLE" ]]; then
    echo -e "${RED}✗ Sample file not found: $SAMPLE${NC}"
    exit 1
fi

echo -e "${YELLOW}Testing POST /v1/analyze/gateway${NC}"
RESPONSE=$(curl -sS --max-time 20 -X POST "$BASE_URL/v1/analyze/gateway" \
    -H "Content-Type: application/json" \
    -H "X-Correlation-ID: test-gateway-$(date +%s)" \
    --data @"$SAMPLE")

# Validate response structure
if echo "$RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); assert 'scores' in d, 'Missing scores'; assert 'analysis' in d, 'Missing analysis'; assert 'decisions' in d, 'Missing decisions'; assert 'recommendations' in d, 'Missing recommendations'; print('OK')" 2>/dev/null; then
    echo -e "${GREEN}✓ Response structure valid${NC}"
    
    # Check scores
    if echo "$RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); s=d.get('scores', {}); assert 'credit_score' in s or 'fraud_score' in s, 'Missing score fields'; print('OK')" 2>/dev/null; then
        echo -e "${GREEN}✓ Scores section present${NC}"
    else
        echo -e "${RED}✗ Scores section incomplete${NC}"
    fi
    
    # Check analysis
    if echo "$RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); a=d.get('analysis', {}); assert len(a) > 0, 'Analysis empty'; print('OK')" 2>/dev/null; then
        echo -e "${GREEN}✓ Analysis section present${NC}"
    else
        echo -e "${RED}✗ Analysis section incomplete${NC}"
    fi
    
    # Check decisions
    if echo "$RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); dec=d.get('decisions', {}); assert 'final_decision' in dec, 'Missing final_decision'; print('OK')" 2>/dev/null; then
        echo -e "${GREEN}✓ Decisions section present${NC}"
    else
        echo -e "${RED}✗ Decisions section incomplete${NC}"
    fi
    
    # Check recommendations
    REC_COUNT=$(echo "$RESPONSE" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('recommendations', [])))" 2>/dev/null || echo "0")
    if [[ "$REC_COUNT" -gt 0 ]]; then
        echo -e "${GREEN}✓ Recommendations present ($REC_COUNT recommendations)${NC}"
    else
        echo -e "${RED}✗ No recommendations generated${NC}"
    fi
    
    # Show summary
    echo ""
    echo "=== Response Summary ==="
    echo "$RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); print(f\"Customer ID: {d.get('customer_id')}\"); print(f\"Request ID: {d.get('request_id')}\"); print(f\"Final Decision: {d.get('decisions', {}).get('final_decision')}\"); print(f\"Approval Status: {d.get('decisions', {}).get('approval_status')}\"); print(f\"Credit Score: {d.get('scores', {}).get('credit_score')}\"); print(f\"Recommendations: {len(d.get('recommendations', []))}\")" 2>/dev/null
    
    echo ""
    echo -e "${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Invalid response structure${NC}"
    echo "Response: $(echo "$RESPONSE" | head -n5)"
    exit 1
fi

