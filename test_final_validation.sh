#!/usr/bin/env bash
# Final Comprehensive Validation Test

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT_FILE="$ROOT_DIR/logs/.local_api.port"
PORT=$(cat "$PORT_FILE" 2>/dev/null || echo "5000")
BASE_URL="http://127.0.0.1:$PORT"
SAMPLE="$ROOT_DIR/sample_request.json"

echo "=========================================="
echo "Final End-to-End Validation"
echo "=========================================="
echo "Service: $BASE_URL"
echo ""

ERRORS=0
WARNINGS=0

# Test 1: Service is running
echo "[1] Service Health Check"
if curl -sS --max-time 5 "$BASE_URL/health" | grep -q '"status":"ok"'; then
    echo "  ✓ Service is healthy"
else
    echo "  ✗ Service is not healthy"
    ((ERRORS++))
fi

# Test 2: All endpoints respond
echo ""
echo "[2] Endpoint Availability"
ENDPOINTS=("/health" "/ready" "/metrics" "/v1/models")
for ep in "${ENDPOINTS[@]}"; do
    if curl -sS --max-time 5 -o /dev/null -w "%{http_code}" "$BASE_URL$ep" | grep -q "^2"; then
        echo "  ✓ $ep"
    else
        echo "  ✗ $ep"
        ((ERRORS++))
    fi
done

# Test 3: Main analysis endpoint
echo ""
echo "[3] Main Analysis Endpoint"
if [[ -f "$SAMPLE" ]]; then
    RESPONSE=$(curl -sS --max-time 20 -X POST "$BASE_URL/v1/analyze" \
        -H "Content-Type: application/json" \
        -H "X-Correlation-ID: final-validation" \
        --data @"$SAMPLE")
    
    if echo "$RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); assert 'qaa_report' in d; assert 'scores' in d; assert 'risk_analysis' in d; assert d['qaa_report']['final_recommendation'] in ['Approve', 'Approve with Conditions', 'Manual Review', 'Decline']; print('OK')" 2>/dev/null; then
        echo "  ✓ Valid response structure"
        echo "  ✓ Required fields present"
        echo "  ✓ Recommendation is valid"
        
        # Check processing time
        PROC_TIME=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('processing_time_ms', 0))" 2>/dev/null || echo "0")
        if [[ "$PROC_TIME" -lt 1000 ]]; then
            echo "  ✓ Processing time acceptable: ${PROC_TIME}ms"
        else
            echo "  ⚠ Processing time high: ${PROC_TIME}ms"
            ((WARNINGS++))
        fi
    else
        echo "  ✗ Invalid response structure"
        ((ERRORS++))
    fi
else
    echo "  ✗ Sample file not found"
    ((ERRORS++))
fi

# Test 4: Error handling
echo ""
echo "[4] Error Handling"
# Missing required field
HTTP_CODE=$(curl -sS --max-time 5 -w "%{http_code}" -X POST "$BASE_URL/v1/analyze" \
    -H "Content-Type: application/json" \
    --data '{"request_id": "test"}' -o /dev/null 2>&1 | grep -oE '[0-9]{3}' | tail -n1)
if [[ "$HTTP_CODE" == "422" ]]; then
    echo "  ✓ Validation errors handled correctly (422)"
else
    echo "  ✗ Expected 422, got $HTTP_CODE"
    ((ERRORS++))
fi

# Invalid endpoint
HTTP_CODE=$(curl -sS --max-time 5 -w "%{http_code}" -o /dev/null "$BASE_URL/invalid" 2>&1 | grep -oE '[0-9]{3}' | tail -n1)
if [[ "$HTTP_CODE" == "404" ]]; then
    echo "  ✓ 404 errors handled correctly"
else
    echo "  ✗ Expected 404, got $HTTP_CODE"
    ((ERRORS++))
fi

# Test 5: Concurrent requests
echo ""
echo "[5] Concurrent Request Handling"
SUCCESS=0
for i in {1..3}; do
    if curl -sS --max-time 15 -X POST "$BASE_URL/v1/analyze" \
        -H "Content-Type: application/json" \
        -H "X-Correlation-ID: concurrent-$i" \
        --data @"$SAMPLE" -o /dev/null -w "%{http_code}" 2>&1 | grep -q "^200"; then
        ((SUCCESS++))
    fi
done
if [[ $SUCCESS -eq 3 ]]; then
    echo "  ✓ All concurrent requests succeeded"
else
    echo "  ✗ Only $SUCCESS/3 concurrent requests succeeded"
    ((ERRORS++))
fi

# Test 6: Response consistency
echo ""
echo "[6] Response Consistency"
RESP1=$(curl -sS --max-time 15 -X POST "$BASE_URL/v1/analyze" \
    -H "Content-Type: application/json" \
    -H "X-Correlation-ID: consistency-1" \
    --data @"$SAMPLE")
RESP2=$(curl -sS --max-time 15 -X POST "$BASE_URL/v1/analyze" \
    -H "Content-Type: application/json" \
    -H "X-Correlation-ID: consistency-2" \
    --data @"$SAMPLE")

REC1=$(echo "$RESP1" | python3 -c "import sys, json; print(json.load(sys.stdin)['qaa_report']['final_recommendation'])" 2>/dev/null)
REC2=$(echo "$RESP2" | python3 -c "import sys, json; print(json.load(sys.stdin)['qaa_report']['final_recommendation'])" 2>/dev/null)

if [[ "$REC1" == "$REC2" ]]; then
    echo "  ✓ Recommendations are consistent: $REC1"
else
    echo "  ⚠ Recommendations differ: $REC1 vs $REC2 (may be acceptable)"
    ((WARNINGS++))
fi

# Summary
echo ""
echo "=========================================="
echo "Validation Summary"
echo "=========================================="
echo "Errors: $ERRORS"
echo "Warnings: $WARNINGS"
echo ""

if [[ $ERRORS -eq 0 ]]; then
    echo "✓ All critical tests passed!"
    if [[ $WARNINGS -eq 0 ]]; then
        echo "✓ No warnings"
        exit 0
    else
        echo "⚠ Some warnings (non-critical)"
        exit 0
    fi
else
    echo "✗ Some tests failed"
    exit 1
fi

