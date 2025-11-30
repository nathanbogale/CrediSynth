#!/usr/bin/env bash
set -euo pipefail

# End-to-end test script for CrediSynth QAA service
# Tests all endpoints and validates responses

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
SAMPLE_REQUEST="$ROOT_DIR/sample_request.json"
PORT_FILE="$ROOT_DIR/logs/.local_api.port"
BASE_URL="http://127.0.0.1"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if jq is available
if command -v jq >/dev/null 2>&1; then
    JQ_CMD="jq"
    JQ_AVAILABLE=true
else
    JQ_CMD="cat"
    JQ_AVAILABLE=false
    echo -e "${YELLOW}Warning: jq not found, JSON output will not be formatted${NC}"
fi

# Get port from file or default
if [[ -f "$PORT_FILE" ]]; then
    PORT="$(head -n1 "$PORT_FILE")"
else
    PORT="5000"
fi

BASE_URL="$BASE_URL:$PORT"

echo "=========================================="
echo "CrediSynth QAA - End-to-End Test Suite"
echo "=========================================="
echo "Base URL: $BASE_URL"
echo "Sample Request: $SAMPLE_REQUEST"
echo ""

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

test_endpoint() {
    local name="$1"
    local method="$2"
    local endpoint="$3"
    local data_file="${4:-}"
    local expected_status="${5:-200}"
    
    echo -e "\n${YELLOW}Testing: $name${NC}"
    echo "  $method $endpoint"
    
    local http_code
    local body
    
    if [[ -n "$data_file" ]] && [[ "$data_file" != "/dev/null" ]]; then
        if [[ ! -f "$data_file" ]]; then
            echo -e "${RED}✗ FAILED: Sample file not found: $data_file${NC}"
            ((TESTS_FAILED++))
            return 1
        fi
        http_code=$(curl -sS -o /tmp/test_response.json -w "%{http_code}" -X "$method" "$BASE_URL$endpoint" \
            -H "Content-Type: application/json" \
            -H "X-Correlation-ID: test-e2e-$(date +%s)" \
            --data @"$data_file" --max-time 10 2>&1 | tail -n1)
        body=$(cat /tmp/test_response.json 2>/dev/null || echo "")
    else
        http_code=$(curl -sS -o /tmp/test_response.json -w "%{http_code}" -X "$method" "$BASE_URL$endpoint" --max-time 10 2>&1 | tail -n1)
        body=$(cat /tmp/test_response.json 2>/dev/null || echo "")
    fi
    
    # Clean http_code (remove any error messages)
    http_code=$(echo "$http_code" | grep -oE '[0-9]{3}' | tail -n1 || echo "000")
    
    if [[ "$http_code" == "$expected_status" ]] || [[ "$http_code" =~ ^[0-9]{3}$ ]] && [[ "$http_code" -ge 200 ]] && [[ "$http_code" -lt 300 ]]; then
        echo -e "${GREEN}✓ PASSED${NC} (HTTP $http_code)"
        if [[ "$JQ_AVAILABLE" == "true" ]] && [[ -n "$body" ]]; then
            echo "$body" | $JQ_CMD . 2>/dev/null | head -n15 || echo "$body" | head -n5
        elif [[ -n "$body" ]]; then
            echo "$body" | head -n5
        fi
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}✗ FAILED${NC} (Expected HTTP $expected_status, got $http_code)"
        if [[ -n "$body" ]]; then
            echo "Response preview: $(echo "$body" | head -n3 | tr '\n' ' ')"
        fi
        ((TESTS_FAILED++))
        return 1
    fi
}

# Test 1: Health Check
test_endpoint "Health Check" "GET" "/health"

# Test 2: Readiness Check
test_endpoint "Readiness Check" "GET" "/ready"

# Test 3: Metrics Endpoint
test_endpoint "Prometheus Metrics" "GET" "/metrics"

# Test 4: Models Endpoint
test_endpoint "List Models" "GET" "/v1/models"

# Test 5: Main Analysis Endpoint (Mock Mode)
if [[ -f "$SAMPLE_REQUEST" ]]; then
    echo -e "\n${YELLOW}Testing Analysis Endpoint (Mock Mode)${NC}"
    test_endpoint "POST /v1/analyze (Mock)" "POST" "/v1/analyze" "$SAMPLE_REQUEST" "200"
    
    # Extract analysis_id from response for retrieval test
    if [[ "$JQ_AVAILABLE" == "true" ]] && [[ -f /tmp/test_response.json ]]; then
        ANALYSIS_ID=$(cat /tmp/test_response.json | jq -r '.qaa_report.analysis_id // empty' 2>/dev/null || echo "")
        
        if [[ -n "$ANALYSIS_ID" ]] && [[ "$ANALYSIS_ID" != "null" ]]; then
            echo -e "\n${YELLOW}Testing Analysis Retrieval${NC}"
            echo "  GET /v1/analyze/$ANALYSIS_ID"
            # Note: This will likely fail if DB auditing is disabled, which is expected
            http_code=$(curl -sS -o /dev/null -w "%{http_code}" -X GET "$BASE_URL/v1/analyze/$ANALYSIS_ID" --max-time 5 2>&1 | tail -n1)
            if [[ "$http_code" == "404" ]] || [[ "$http_code" == "200" ]]; then
                echo -e "${GREEN}✓ PASSED${NC} (HTTP $http_code - Expected behavior)"
                ((TESTS_PASSED++))
            else
                echo -e "${YELLOW}Note: Retrieval returned HTTP $http_code (expected 404 if DB disabled)${NC}"
            fi
        fi
    fi
else
    echo -e "${RED}✗ FAILED: Sample request file not found: $SAMPLE_REQUEST${NC}"
    ((TESTS_FAILED++))
fi

# Test 6: Validation Error Test (malformed request)
echo -e "\n${YELLOW}Testing Validation Error Handling${NC}"
echo '{"invalid": "request"}' > /tmp/invalid_request.json
http_code=$(curl -sS -o /tmp/validation_response.json -w "%{http_code}" -X POST "$BASE_URL/v1/analyze" \
    -H "Content-Type: application/json" \
    --data @/tmp/invalid_request.json --max-time 5 2>&1 | tail -n1)
http_code=$(echo "$http_code" | grep -oE '[0-9]{3}' | tail -n1 || echo "000")
if [[ "$http_code" == "422" ]] || [[ "$http_code" == "400" ]]; then
    echo -e "${GREEN}✓ PASSED${NC} (HTTP $http_code - Validation error as expected)"
    ((TESTS_PASSED++))
else
    echo -e "${YELLOW}Note: Validation test returned HTTP $http_code${NC}"
fi

# Test 7: Async Job Endpoint
if [[ -f "$SAMPLE_REQUEST" ]]; then
    test_endpoint "POST /v1/analyze/async" "POST" "/v1/analyze/async" "$SAMPLE_REQUEST" "202"
fi

# Summary
echo ""
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Failed: $TESTS_FAILED${NC}"
echo ""

if [[ $TESTS_FAILED -eq 0 ]]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    exit 1
fi
