# Severity Mapper Production Test

## Overview

This test script validates that the code-based severity mapper is working correctly in production. It tests the `/experity/map` endpoint to ensure severity values are correctly extracted from `complaint.painScale` and merged into the response.

## Test Coverage

The test covers the following scenarios:

1. **Normal Cases**
   - painScale: 7 → severity: 7
   - painScale: 3 → severity: 3
   - painScale: 10 → severity: 10 (maximum)
   - painScale: 0 → severity: 0 (minimum)

2. **Missing Values**
   - No painScale → severity: 5 (default)

3. **Type Conversion**
   - String painScale: "8" → severity: 8
   - Float painScale: 7.5 → severity: 7 (truncated)

4. **Range Clamping**
   - painScale: 15 → severity: 10 (clamped to max)
   - painScale: -5 → severity: 0 (clamped to min)

5. **Data Type Validation**
   - Severity is always numeric (never string)
   - Severity is always integer (0-10)

## Usage

### Basic Usage

```bash
python scripts/test_severity_mapper_production.py
```

### With Environment Variables

```bash
export API_BASE_URL="https://app-97926.on-aptible.com"
export INTELLIVISIT_STAGING_HMAC_SECRET="your-secret-key"
export STAGING_CLIENT_ID="your-client-id"

python scripts/test_severity_mapper_production.py
```

### Environment Variables

- `API_BASE_URL`: Production API URL (default: `https://app-97926.on-aptible.com`)
- `INTELLIVISIT_STAGING_HMAC_SECRET`: HMAC secret for authentication
- `STAGING_CLIENT_ID`: Client ID for test encounters

## What the Test Validates

1. **Severity Extraction**
   - Severity is correctly extracted from `chiefComplaints[].painScale`
   - Default value (5) is used when painScale is missing

2. **Severity Merging**
   - Code-based severity overwrites AI-generated severity
   - Severity values match expected values from source painScale

3. **Data Type**
   - Severity is numeric (int), not string
   - Severity is within valid range (0-10)

4. **Edge Cases**
   - String painScale values are converted to int
   - Float painScale values are truncated to int
   - Out-of-range values are clamped

## Expected Output

The test will output:

1. **Test Encounter Details**
   - Encounter ID
   - Source complaints with painScale values

2. **Response Validation**
   - For each complaint:
     - ✅/❌ Status
     - Complaint ID
     - Actual severity value
     - Expected severity value
     - Match status

3. **Summary**
   - Total complaints tested
   - Valid severity count
   - Invalid severity count
   - Expected vs Actual comparison

4. **Final Result**
   - ✅ ALL TESTS PASSED: If all validations pass
   - ❌ SOME TESTS FAILED: If any validation fails

## Example Output

```
================================================================================
Testing /experity/map endpoint - Severity Mapper Validation
================================================================================

Test Encounter ID: 123e4567-e89b-12d3-a456-426614174000

Source Complaints with painScale:
  1. 'chest pain': painScale=7, expected severity=7
  2. 'headache': painScale=3, expected severity=3
  3. 'severe pain': painScale=10, expected severity=10
  ...

================================================================================
Severity Validation Results
================================================================================

✅ Complaint: 'chest pain'
   Complaint ID: abc-123-def
   Severity: 7
   Expected: 7 (from painScale: 7)
   ✅ Matches expected value

✅ Complaint: 'headache'
   Complaint ID: xyz-456-ghi
   Severity: 3
   Expected: 3 (from painScale: 3)
   ✅ Matches expected value

...

================================================================================
Summary
================================================================================
Total complaints: 8
Valid severity: 8
Invalid severity: 0

Expected vs Actual Severity:
  Matched: 8/8
  Mismatched: 0/8

✅ ALL TESTS PASSED: Severity mapper is working correctly
```

## Troubleshooting

### Test Fails with "Severity mismatch"

This indicates that the code-based severity is not being applied correctly. Check:
- Server logs for severity extraction/merging
- Verify the endpoint code is deployed
- Check if there are any errors in the merge process

### Test Fails with "Severity is string"

This indicates the severity value is not being converted to numeric. This should be handled by the mapper, but may indicate an issue with the merge function.

### Request Timeout

If the request times out:
- Check API URL is correct
- Verify network connectivity
- Check if the endpoint is responding

### Authentication Error

If you get authentication errors:
- Verify `INTELLIVISIT_STAGING_HMAC_SECRET` is correct
- Check HMAC signature generation
- Verify timestamp format

## Related Files

- `app/utils/experity_mapper/complaint/severity_mapper.py` - Severity extraction logic
- `app/utils/experity_mapper.py` - Merge function
- `app/api/routes/queue.py` - Endpoint integration
- `tests/utils/test_severity_mapper.py` - Unit tests
