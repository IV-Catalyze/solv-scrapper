#!/bin/bash
# Test script for new PATCH queue endpoints
# This script tests the new endpoints with camelCase field names

set -e

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
HMAC_SECRET="${HMAC_SECRET:-test-secret-key}"

echo "Testing PATCH /queue/{queue_id}/status and PATCH /queue/{queue_id}/requeue endpoints"
echo "API Base URL: $API_BASE_URL"
echo ""

# Function to generate HMAC signature
generate_hmac() {
    local method=$1
    local path=$2
    local body=$3
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    
    # Create canonical string
    local body_hash=$(echo -n "$body" | openssl dgst -sha256 -binary | base64)
    local canonical_string="${method}\n${path}\n${timestamp}\n${body_hash}"
    
    # Generate HMAC signature
    local signature=$(echo -n "$canonical_string" | openssl dgst -sha256 -hmac "$HMAC_SECRET" -binary | base64)
    
    echo "$timestamp|$signature"
}

# Get a queue entry first
echo "1. Getting a queue entry..."
GET_PATH="/queue?limit=1"
GET_BODY=""
GET_AUTH=$(generate_hmac "GET" "$GET_PATH" "$GET_AUTH")
GET_TIMESTAMP=$(echo $GET_AUTH | cut -d'|' -f1)
GET_SIGNATURE=$(echo $GET_AUTH | cut -d'|' -f2)

GET_RESPONSE=$(curl -s -w "\n%{http_code}" -X GET "$API_BASE_URL$GET_PATH" \
    -H "X-Timestamp: $GET_TIMESTAMP" \
    -H "X-Signature: $GET_SIGNATURE" \
    -H "Content-Type: application/json")

GET_HTTP_CODE=$(echo "$GET_RESPONSE" | tail -n1)
GET_BODY=$(echo "$GET_RESPONSE" | head -n-1)

if [ "$GET_HTTP_CODE" != "200" ]; then
    echo "❌ Failed to get queue entry. HTTP $GET_HTTP_CODE"
    echo "$GET_BODY"
    exit 1
fi

QUEUE_ID=$(echo "$GET_BODY" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data[0]['queue_id'] if isinstance(data, list) and len(data) > 0 else '')" 2>/dev/null || echo "")

if [ -z "$QUEUE_ID" ]; then
    echo "❌ No queue entries found. Cannot test endpoints."
    exit 1
fi

echo "✅ Found queue entry: $QUEUE_ID"
echo ""

# Test 1: Update status to DONE with experityActions (camelCase)
echo "2. Testing PATCH /queue/{queue_id}/status with status=DONE and experityActions (camelCase)..."
STATUS_PATH="/queue/$QUEUE_ID/status"
STATUS_BODY='{"status":"DONE","experityActions":{"vitals":{"temperature":98.6},"complaints":[]}}'
STATUS_AUTH=$(generate_hmac "PATCH" "$STATUS_PATH" "$STATUS_BODY")
STATUS_TIMESTAMP=$(echo $STATUS_AUTH | cut -d'|' -f1)
STATUS_SIGNATURE=$(echo $STATUS_AUTH | cut -d'|' -f2)

STATUS_RESPONSE=$(curl -s -w "\n%{http_code}" -X PATCH "$API_BASE_URL$STATUS_PATH" \
    -H "X-Timestamp: $STATUS_TIMESTAMP" \
    -H "X-Signature: $STATUS_SIGNATURE" \
    -H "Content-Type: application/json" \
    -d "$STATUS_BODY")

STATUS_HTTP_CODE=$(echo "$STATUS_RESPONSE" | tail -n1)
STATUS_BODY_RESPONSE=$(echo "$STATUS_RESPONSE" | head -n-1)

if [ "$STATUS_HTTP_CODE" == "200" ]; then
    echo "✅ Status update successful"
    echo "$STATUS_BODY_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$STATUS_BODY_RESPONSE"
else
    echo "❌ Status update failed. HTTP $STATUS_HTTP_CODE"
    echo "$STATUS_BODY_RESPONSE"
fi
echo ""

# Test 2: Update status to ERROR with errorMessage and incrementAttempts (camelCase)
echo "3. Testing PATCH /queue/{queue_id}/status with status=ERROR, errorMessage, and incrementAttempts (camelCase)..."
ERROR_PATH="/queue/$QUEUE_ID/status"
ERROR_BODY='{"status":"ERROR","errorMessage":"Test error message","incrementAttempts":true}'
ERROR_AUTH=$(generate_hmac "PATCH" "$ERROR_PATH" "$ERROR_BODY")
ERROR_TIMESTAMP=$(echo $ERROR_AUTH | cut -d'|' -f1)
ERROR_SIGNATURE=$(echo $ERROR_AUTH | cut -d'|' -f2)

ERROR_RESPONSE=$(curl -s -w "\n%{http_code}" -X PATCH "$API_BASE_URL$ERROR_PATH" \
    -H "X-Timestamp: $ERROR_TIMESTAMP" \
    -H "X-Signature: $ERROR_SIGNATURE" \
    -H "Content-Type: application/json" \
    -d "$ERROR_BODY")

ERROR_HTTP_CODE=$(echo "$ERROR_RESPONSE" | tail -n1)
ERROR_BODY_RESPONSE=$(echo "$ERROR_RESPONSE" | head -n-1)

if [ "$ERROR_HTTP_CODE" == "200" ]; then
    echo "✅ Error status update successful"
    echo "$ERROR_BODY_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$ERROR_BODY_RESPONSE"
else
    echo "❌ Error status update failed. HTTP $ERROR_HTTP_CODE"
    echo "$ERROR_BODY_RESPONSE"
fi
echo ""

# Test 3: Requeue with priority and errorMessage (camelCase)
echo "4. Testing PATCH /queue/{queue_id}/requeue with priority and errorMessage (camelCase)..."
REQUEUE_PATH="/queue/$QUEUE_ID/requeue"
REQUEUE_BODY='{"priority":"HIGH","errorMessage":"Requeued for retry"}'
REQUEUE_AUTH=$(generate_hmac "PATCH" "$REQUEUE_PATH" "$REQUEUE_BODY")
REQUEUE_TIMESTAMP=$(echo $REQUEUE_AUTH | cut -d'|' -f1)
REQUEUE_SIGNATURE=$(echo $REQUEUE_AUTH | cut -d'|' -f2)

REQUEUE_RESPONSE=$(curl -s -w "\n%{http_code}" -X PATCH "$API_BASE_URL$REQUEUE_PATH" \
    -H "X-Timestamp: $REQUEUE_TIMESTAMP" \
    -H "X-Signature: $REQUEUE_SIGNATURE" \
    -H "Content-Type: application/json" \
    -d "$REQUEUE_BODY")

REQUEUE_HTTP_CODE=$(echo "$REQUEUE_RESPONSE" | tail -n1)
REQUEUE_BODY_RESPONSE=$(echo "$REQUEUE_RESPONSE" | head -n-1)

if [ "$REQUEUE_HTTP_CODE" == "200" ]; then
    echo "✅ Requeue successful"
    echo "$REQUEUE_BODY_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$REQUEUE_BODY_RESPONSE"
else
    echo "❌ Requeue failed. HTTP $REQUEUE_HTTP_CODE"
    echo "$REQUEUE_BODY_RESPONSE"
fi
echo ""

# Test 4: Test invalid status
echo "5. Testing PATCH /queue/{queue_id}/status with invalid status..."
INVALID_PATH="/queue/$QUEUE_ID/status"
INVALID_BODY='{"status":"INVALID_STATUS"}'
INVALID_AUTH=$(generate_hmac "PATCH" "$INVALID_PATH" "$INVALID_BODY")
INVALID_TIMESTAMP=$(echo $INVALID_AUTH | cut -d'|' -f1)
INVALID_SIGNATURE=$(echo $INVALID_AUTH | cut -d'|' -f2)

INVALID_RESPONSE=$(curl -s -w "\n%{http_code}" -X PATCH "$API_BASE_URL$INVALID_PATH" \
    -H "X-Timestamp: $INVALID_TIMESTAMP" \
    -H "X-Signature: $INVALID_SIGNATURE" \
    -H "Content-Type: application/json" \
    -d "$INVALID_BODY")

INVALID_HTTP_CODE=$(echo "$INVALID_RESPONSE" | tail -n1)

if [ "$INVALID_HTTP_CODE" == "400" ]; then
    echo "✅ Invalid status correctly rejected (400)"
else
    echo "❌ Expected 400 for invalid status, got $INVALID_HTTP_CODE"
fi
echo ""

# Test 5: Test invalid priority
echo "6. Testing PATCH /queue/{queue_id}/requeue with invalid priority..."
INVALID_PRIORITY_PATH="/queue/$QUEUE_ID/requeue"
INVALID_PRIORITY_BODY='{"priority":"INVALID_PRIORITY"}'
INVALID_PRIORITY_AUTH=$(generate_hmac "PATCH" "$INVALID_PRIORITY_PATH" "$INVALID_PRIORITY_BODY")
INVALID_PRIORITY_TIMESTAMP=$(echo $INVALID_PRIORITY_AUTH | cut -d'|' -f1)
INVALID_PRIORITY_SIGNATURE=$(echo $INVALID_PRIORITY_AUTH | cut -d'|' -f2)

INVALID_PRIORITY_RESPONSE=$(curl -s -w "\n%{http_code}" -X PATCH "$API_BASE_URL$INVALID_PRIORITY_PATH" \
    -H "X-Timestamp: $INVALID_PRIORITY_TIMESTAMP" \
    -H "X-Signature: $INVALID_PRIORITY_SIGNATURE" \
    -H "Content-Type: application/json" \
    -d "$INVALID_PRIORITY_BODY")

INVALID_PRIORITY_HTTP_CODE=$(echo "$INVALID_PRIORITY_RESPONSE" | tail -n1)

if [ "$INVALID_PRIORITY_HTTP_CODE" == "400" ]; then
    echo "✅ Invalid priority correctly rejected (400)"
else
    echo "❌ Expected 400 for invalid priority, got $INVALID_PRIORITY_HTTP_CODE"
fi
echo ""

echo "✅ All tests completed!"

