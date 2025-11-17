#!/bin/bash
# Simple test script for the API

echo "🧪 Testing Patient Data API"
echo "=========================="
echo ""

# Generate a unique EMR ID
EMR_ID="TEST_$(date +%s)"

echo "📤 Sending test patient data..."
echo "EMR ID: $EMR_ID"
echo ""

RESPONSE=$(curl -s -X POST "http://localhost:8000/patients/create" \
  -H "Content-Type: application/json" \
  -d "{
    \"emr_id\": \"$EMR_ID\",
    \"location_id\": \"AXjwbE\",
    \"location_name\": \"Exer Urgent Care - Demo\",
    \"legalFirstName\": \"Test\",
    \"legalLastName\": \"Patient\",
    \"dob\": \"01/15/1990\",
    \"mobilePhone\": \"(555) 123-4567\",
    \"sexAtBirth\": \"Male\",
    \"reasonForVisit\": \"Test API Integration\",
    \"status\": \"checked_in\"
  }")

echo "📥 Response:"
echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
echo ""

if echo "$RESPONSE" | grep -q "created successfully\|updated"; then
    echo "✅ SUCCESS! Patient data was saved via API"
    exit 0
else
    echo "❌ FAILED! Check the error message above"
    exit 1
fi

