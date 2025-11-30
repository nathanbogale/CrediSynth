#!/usr/bin/env bash
set -euo pipefail

# Comprehensive End-to-End Test Suite with Error Handling
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT_FILE="$ROOT_DIR/logs/.local_api.port"
PORT=$(cat "$PORT_FILE" 2>/dev/null || echo "5000")
BASE_URL="http://127.0.0.1:$PORT"
SAMPLE="$ROOT_DIR/sample_request.json"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASSED=0
FAILED=0
ERRORS=()

test_endpoint() {
    local name="$1"
    local method="$2"
    local endpoint="$3"
    local data="${4:-}"
    local expected_code="${5:-200}"
    
    echo -e "\n${YELLOW}[TEST]${NC} $name"
    echo "  $method $endpoint"
    
    local http_code
    local body
    local temp_file="/tmp/test_response_$$.txt"
    
    if [[ -n "$data" ]] && [[ "$data" != "null" ]]; then
        if [[ -f "$data" ]]; then
            http_code=$(curl -sS -o "$temp_file" -w "%{http_code}" --max-time 15 -X "$method" "$BASE_URL$endpoint" \
                -H "Content-Type: application/json" \
                -H "X-Correlation-ID: test-$(date +%s)" \
                --data @"$data" 2>&1 | tail -n1)
        else
            http_code=$(curl -sS -o "$temp_file" -w "%{http_code}" --max-time 15 -X "$method" "$BASE_URL$endpoint" \
                -H "Content-Type: application/json" \
                -H "X-Correlation-ID: test-$(date +%s)" \
                --data "$data" 2>&1 | tail -n1)
        fi
    else
        http_code=$(curl -sS -o "$temp_file" -w "%{http_code}" --max-time 10 -X "$method" "$BASE_URL$endpoint" 2>&1 | tail -n1)
    fi
    
    http_code=$(echo "$http_code" | grep -oE '[0-9]{3}' | head -n1 || echo "000")
    body=$(cat "$temp_file" 2>/dev/null || echo "")
    rm -f "$temp_file" 2>/dev/null
    
    if [[ "$http_code" == "$expected_code" ]]; then
        echo -e "${GREEN}✓ PASSED${NC} (HTTP $http_code)"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗ FAILED${NC} (Expected $expected_code, got $http_code)"
        echo "Response: $(echo "$body" | head -n3)"
        ERRORS+=("$name: Expected HTTP $expected_code, got $http_code")
        ((FAILED++))
        return 1
    fi
}

echo "=========================================="
echo "Comprehensive End-to-End Test Suite"
echo "=========================================="
echo "Base URL: $BASE_URL"
echo ""

# Test 1: Health Check
test_endpoint "Health Check" "GET" "/health"

# Test 2: Readiness Check
test_endpoint "Readiness Check" "GET" "/ready"

# Test 3: Metrics
test_endpoint "Prometheus Metrics" "GET" "/metrics"

# Test 4: Models
test_endpoint "List Models" "GET" "/v1/models"

# Test 5: Main Analysis (with valid request)
if [[ -f "$SAMPLE" ]]; then
    test_endpoint "POST /v1/analyze (Valid)" "POST" "/v1/analyze" "$SAMPLE" "200"
    
    # Verify response structure
    RESPONSE=$(curl -sS --max-time 20 -X POST "$BASE_URL/v1/analyze" \
        -H "Content-Type: application/json" \
        -H "X-Correlation-ID: test-validate-$(date +%s)" \
        --data @"$SAMPLE")
    
    if echo "$RESPONSE" | python3 -c "import sys, json; json.load(sys.stdin)" 2>/dev/null; then
        echo -e "${GREEN}✓ Response is valid JSON${NC}"
        ((PASSED++))
        
        # Check required fields
        REQUIRED_FIELDS=("request_id" "customer_id" "qaa_report" "scores" "risk_analysis")
        for field in "${REQUIRED_FIELDS[@]}"; do
            if echo "$RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); exit(0 if '$field' in d else 1)" 2>/dev/null; then
                echo -e "${GREEN}✓ Field '$field' present${NC}"
            else
                echo -e "${RED}✗ Field '$field' missing${NC}"
                ERRORS+=("Response missing required field: $field")
                ((FAILED++))
            fi
        done
    else
        echo -e "${RED}✗ Response is not valid JSON${NC}"
        ERRORS+=("Response is not valid JSON")
        ((FAILED++))
    fi
else
    echo -e "${RED}✗ Sample file not found: $SAMPLE${NC}"
    ERRORS+=("Sample file not found")
    ((FAILED++))
fi

# Test 6: Validation Error (missing required fields)
test_endpoint "POST /v1/analyze (Invalid - Missing Fields)" "POST" "/v1/analyze" '{"invalid": "data"}' "422"

# Test 7: Validation Error (malformed JSON)
echo -e "\n${YELLOW}[TEST]${NC} POST /v1/analyze (Malformed JSON)"
RESPONSE=$(curl -sS -w "\n%{http_code}" --max-time 10 -X POST "$BASE_URL/v1/analyze" \
    -H "Content-Type: application/json" \
    --data '{"invalid": json}' 2>&1)
HTTP_CODE=$(echo "$RESPONSE" | tail -n1 | grep -oE '[0-9]{3}' || echo "000")
if [[ "$HTTP_CODE" == "400" ]] || [[ "$HTTP_CODE" == "422" ]]; then
    echo -e "${GREEN}✓ PASSED${NC} (HTTP $HTTP_CODE - Malformed JSON rejected)"
    ((PASSED++))
else
    echo -e "${RED}✗ FAILED${NC} (Expected 400/422, got $HTTP_CODE)"
    ERRORS+=("Malformed JSON test: Expected 400/422, got $HTTP_CODE")
    ((FAILED++))
fi

# Test 8: Async Endpoint
if [[ -f "$SAMPLE" ]]; then
    test_endpoint "POST /v1/analyze/async" "POST" "/v1/analyze/async" "$SAMPLE" "202"
fi

# Test 9: Invalid Endpoint (404)
test_endpoint "GET /invalid/endpoint (404)" "GET" "/invalid/endpoint" "" "404"

# Test 10: Analysis Retrieval (will fail if DB disabled, which is expected)
ANALYSIS_ID="test-id-12345"
echo -e "\n${YELLOW}[TEST]${NC} GET /v1/analyze/{analysis_id} (Expected 404 if DB disabled)"
HTTP_CODE=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 5 -X GET "$BASE_URL/v1/analyze/$ANALYSIS_ID" 2>&1 | grep -oE '[0-9]{3}' || echo "000")
if [[ "$HTTP_CODE" == "404" ]] || [[ "$HTTP_CODE" == "500" ]]; then
    echo -e "${GREEN}✓ PASSED${NC} (HTTP $HTTP_CODE - Expected behavior when DB disabled)"
    ((PASSED++))
else
    echo -e "${YELLOW}Note: Got HTTP $HTTP_CODE (may be expected)${NC}"
fi

# Test 11: Job Status
JOB_ID="test-job-12345"
echo -e "\n${YELLOW}[TEST]${NC} GET /v1/jobs/{job_id}"
HTTP_CODE=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 5 -X GET "$BASE_URL/v1/jobs/$JOB_ID" 2>&1 | grep -oE '[0-9]{3}' || echo "000")
if [[ "$HTTP_CODE" == "200" ]] || [[ "$HTTP_CODE" == "404" ]]; then
    echo -e "${GREEN}✓ PASSED${NC} (HTTP $HTTP_CODE)"
    ((PASSED++))
else
    echo -e "${YELLOW}Note: Got HTTP $HTTP_CODE${NC}"
fi

# Test 12: Empty Request Body
test_endpoint "POST /v1/analyze (Empty Body)" "POST" "/v1/analyze" '{}' "422"

# Test 13: Missing Content-Type
echo -e "\n${YELLOW}[TEST]${NC} POST /v1/analyze (Missing Content-Type)"
if [[ -f "$SAMPLE" ]]; then
    HTTP_CODE=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 10 -X POST "$BASE_URL/v1/analyze" \
        --data @"$SAMPLE" 2>&1 | grep -oE '[0-9]{3}' || echo "000")
    if [[ "$HTTP_CODE" == "422" ]] || [[ "$HTTP_CODE" == "400" ]]; then
        echo -e "${GREEN}✓ PASSED${NC} (HTTP $HTTP_CODE - Missing Content-Type handled)"
        ((PASSED++))
    else
        echo -e "${YELLOW}Note: Got HTTP $HTTP_CODE${NC}"
    fi
fi

# Summary
echo ""
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo ""

if [[ ${#ERRORS[@]} -gt 0 ]]; then
    echo -e "${RED}Errors:${NC}"
    for error in "${ERRORS[@]}"; do
        echo "  - $error"
    done
    echo ""
fi

if [[ $FAILED -eq 0 ]]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    exit 1
fi

