# Testing Guide: EMR ID Detection and API Integration

## Overview
This guide helps you test and debug the critical workflow where patient data is automatically sent to your API when an EMR ID becomes available.

## Critical Workflow

1. **Form Submission** → Patient data captured → Saved as `pending` (EMR ID = null)
2. **API Response Monitoring** → Intercepts Solvhealth API responses
3. **EMR ID Detection** → When `integration_status[0].emr_id` becomes non-null
4. **API Request Sent** → Complete patient data sent to `/patients/create`
5. **Database Updated** → Patient saved to `patients` table

## Testing Steps

### 1. Verify API Server is Running

```bash
# Check if API is running
curl http://localhost:8000/patients

# Test API endpoint directly
curl -X POST http://localhost:8000/patients/create \
  -H "Content-Type: application/json" \
  -d '{
    "emr_id": "TEST_123",
    "legalFirstName": "Test",
    "legalLastName": "Patient"
  }'
```

### 2. Run Test Script

```bash
python3 test_emr_flow.py
```

This will:
- Check API availability
- Test sending patient data to API
- Verify the complete flow

### 3. Monitor Logs

When running the monitor, you should see:

#### When API Response is Intercepted:
```
🔍 Intercepted Solvhealth API response:
   URL: https://api-manage.solvhealth.com/v1/bookings/...
   Status: 200
   📋 Response body structure: <class 'dict'>
   📋 Response keys: ['data']
   📋 Data keys: ['id', 'integration_status', ...]
   📋 Found integration_status in data
   📋 integration_status[0].emr_id = null (type: <class 'NoneType'>)
```

#### When EMR ID is Found:
```
📍 Found EMR ID in integration_status: 2316881
   📋 Integration status: completed
   📋 Booking ID: 12345
   📋 Patient: John Doe

🌐 API response contains EMR ID: 2316881
   URL: https://api-manage.solvhealth.com/v1/bookings/...
   Patient: John Doe
   ✅ Matched with pending patient!
      Match by name: John Doe

   🔄 Calling update_patient_emr_id() with patient data...
      EMR ID: 2316881
      Patient: John Doe

============================================================
🚀 CRITICAL: EMR ID FOUND - PREPARING TO SEND TO API
============================================================
   EMR ID: 2316881
   Patient: John Doe
   USE_API: True
   HTTPX_AVAILABLE: True
   Patient data keys: ['emr_id', 'legalFirstName', ...]
   📡 Sending patient data to API...
   📤 API Request Details:
      URL: http://localhost:8000/patients/create
      Method: POST
      Payload: {...}
   🔄 Sending HTTP request...
   📥 Response received: 200
   ✅ Patient data sent to API successfully (EMR ID: 2316881)
   ✅ Patient data successfully sent to API (EMR ID: 2316881)
============================================================
```

## Debugging Checklist

### If Data is Not Coming:

1. **Check API Server**
   - Is it running? `curl http://localhost:8000/patients`
   - Is it on the correct port? Check `.env` file for `API_PORT`

2. **Check Environment Variables**
   ```bash
   # In .env file:
   USE_API=true
   API_HOST=localhost
   API_PORT=8000
   ```

3. **Check API Response Interception**
   - Look for: `🔍 Intercepted Solvhealth API response:`
   - If not appearing, the monitor might not be intercepting responses
   - Check browser console for network errors

4. **Check EMR ID Detection**
   - Look for: `📍 Found EMR ID in integration_status:`
   - If EMR ID is `null`, wait 60-120 seconds for it to be assigned
   - Check the response structure matches expected format

5. **Check Patient Matching**
   - Look for: `✅ Matched with pending patient!`
   - If not matching, check name/phone matching logic
   - Verify pending patient exists in `pending_patients` list

6. **Check API Request**
   - Look for: `📤 API Request Details:`
   - Verify URL, payload, and headers are correct
   - Check for authentication errors

7. **Check API Response**
   - Look for: `📥 Response received: 200`
   - If status is not 200/201, check error message
   - Verify API endpoint is working with test script

## Common Issues

### Issue: "API is not available"
**Solution**: Start the API server with `python3 run_all.py` or `python3 api.py`

### Issue: "EMR ID found but no matching patient"
**Solution**: 
- Check if form was submitted and patient is in `pending_patients`
- Verify name/phone matching logic
- Check pending patients table in database

### Issue: "Failed to send to API"
**Solution**:
- Check API server logs
- Verify API endpoint exists: `/patients/create`
- Check authentication if required
- Verify network connectivity

### Issue: "No API responses intercepted"
**Solution**:
- Check if browser is actually making API calls
- Verify URL pattern matching in `handle_response`
- Check Playwright is properly intercepting responses

## Manual Testing

### Test 1: Direct API Call
```bash
python3 test_emr_flow.py
```

### Test 2: Check Database
```bash
python3 check_db_records.py
```

### Test 3: Monitor Logs
Watch the monitor output for:
- Form submissions
- API response interceptions
- EMR ID detections
- API requests sent

## Expected Behavior

1. **Form Submitted** → `💾 Saved to database (pending)`
2. **API Response (null EMR)** → `📋 integration_status[0].emr_id = null` (ignored)
3. **API Response (EMR ID)** → `📍 Found EMR ID: 2316881`
4. **Patient Matched** → `✅ Matched with pending patient!`
5. **API Request** → `📡 Sending patient data to API...`
6. **API Success** → `✅ Patient data sent to API successfully`
7. **Database Updated** → `✅ Pending patient promoted to patients table`

## Next Steps

If data is still not coming:
1. Check all logs carefully
2. Verify each step in the workflow
3. Test API endpoint directly
4. Check database for pending patients
5. Verify EMR ID is actually being assigned in Solvhealth

