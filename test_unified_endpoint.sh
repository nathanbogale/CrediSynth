#!/usr/bin/env bash
# Test script for unified /v1/analyze endpoint

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT_FILE="$ROOT_DIR/logs/.local_api.port"
PORT=$(cat "$PORT_FILE" 2>/dev/null || echo "5000")
BASE_URL="http://127.0.0.1:$PORT"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASSED=0
FAILED=0

test_endpoint() {
    local name="$1"
    local data_file="$2"
    local expected_type="$3"
    
    echo -e "\n${YELLOW}Testing: $name${NC}"
    
    RESPONSE=$(curl -sS --max-time 20 -X POST "$BASE_URL/v1/analyze" \
        -H "Content-Type: application/json" \
        -H "X-Correlation-ID: test-$(date +%s)" \
        --data @"$data_file" 2>&1)
    
    if echo "$RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin)" 2>/dev/null; then
        if [[ "$expected_type" == "gateway" ]]; then
            if echo "$RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); assert 'scores' in d and 'decisions' in d and 'recommendations' in d; print('OK')" 2>/dev/null; then
                echo -e "${GREEN}✓ PASSED${NC} (Gateway format detected and processed)"
                ((PASSED++))
                return 0
            fi
        elif [[ "$expected_type" == "qse" ]]; then
            if echo "$RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); assert 'qaa_report' in d; print('OK')" 2>/dev/null; then
                echo -e "${GREEN}✓ PASSED${NC} (QSE format detected and processed)"
                ((PASSED++))
                return 0
            fi
        fi
    fi
    
    echo -e "${RED}✗ FAILED${NC}"
    echo "Response: $(echo "$RESPONSE" | head -n3)"
    ((FAILED++))
    return 1
}

echo "=========================================="
echo "Unified /v1/analyze Endpoint Test"
echo "=========================================="
echo "Base URL: $BASE_URL"
echo ""

# Test Gateway format
if [[ -f "$ROOT_DIR/examples/gateway_assessment_sample.json" ]]; then
    test_endpoint "Gateway Format Detection" "$ROOT_DIR/examples/gateway_assessment_sample.json" "gateway"
fi

# Test QSE format
if [[ -f "$ROOT_DIR/sample_request.json" ]]; then
    test_endpoint "QSE Format Detection" "$ROOT_DIR/sample_request.json" "qse"
fi

# Summary
echo ""
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo ""

if [[ $FAILED -eq 0 ]]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    exit 1
fi

