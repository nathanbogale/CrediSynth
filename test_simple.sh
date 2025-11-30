#!/usr/bin/env bash
# Simple end-to-end test script

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT_FILE="$ROOT_DIR/logs/.local_api.port"
PORT=$(cat "$PORT_FILE" 2>/dev/null || echo "5000")
BASE_URL="http://127.0.0.1:$PORT"
SAMPLE="$ROOT_DIR/sample_request.json"

echo "Testing CrediSynth QAA on $BASE_URL"
echo ""

# Test 1: Health
echo "1. Health Check:"
curl -sS --max-time 5 "$BASE_URL/health" | python3 -m json.tool && echo "✓" || echo "✗"
echo ""

# Test 2: Ready
echo "2. Readiness Check:"
curl -sS --max-time 5 "$BASE_URL/ready" | python3 -m json.tool && echo "✓" || echo "✗"
echo ""

# Test 3: Models
echo "3. Models Endpoint:"
curl -sS --max-time 5 "$BASE_URL/v1/models" | python3 -m json.tool && echo "✓" || echo "✗"
echo ""

# Test 4: Analyze
echo "4. Analyze Endpoint:"
if [[ -f "$SAMPLE" ]]; then
    RESPONSE=$(curl -sS --max-time 20 -X POST "$BASE_URL/v1/analyze" \
        -H "Content-Type: application/json" \
        -H "X-Correlation-ID: test-simple-$(date +%s)" \
        --data @"$SAMPLE")
    echo "$RESPONSE" | python3 -m json.tool | head -30
    if echo "$RESPONSE" | grep -q "qaa_report"; then
        echo "✓ Analysis successful"
    else
        echo "✗ Analysis failed"
    fi
else
    echo "✗ Sample file not found"
fi
echo ""

# Test 5: Metrics
echo "5. Metrics Endpoint:"
curl -sS --max-time 5 "$BASE_URL/metrics" | head -5 && echo "✓" || echo "✗"
echo ""

echo "All tests completed!"

