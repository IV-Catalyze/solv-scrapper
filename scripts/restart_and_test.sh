#!/bin/bash
echo "🔄 Restarting API server and testing..."
echo ""

# Find and kill process on port 8000
PID=$(lsof -ti:8000 2>/dev/null)
if [ ! -z "$PID" ]; then
    echo "Stopping server on port 8000 (PID: $PID)..."
    kill $PID 2>/dev/null
    sleep 2
fi

# Start server in background
echo "Starting API server..."
python3 -m uvicorn app.api.routes:app > /tmp/api_server.log 2>&1 &
SERVER_PID=$!
echo "Server started (PID: $SERVER_PID)"
echo "Waiting for server to start..."
sleep 3

# Test the API
echo ""
echo "🧪 Testing API..."
EMR_ID="TEST_$(date +%s)"
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

echo "Response:"
echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"

if echo "$RESPONSE" | grep -q "created successfully\|updated"; then
    echo ""
    echo "✅ SUCCESS! API is working correctly!"
    echo "Server is running in background (PID: $SERVER_PID)"
    echo "To stop it: kill $SERVER_PID"
else
    echo ""
    echo "❌ Test failed. Check server logs: tail -f /tmp/api_server.log"
fi
