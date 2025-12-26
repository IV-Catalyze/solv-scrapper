# Root Cause Analysis: 504/502 Errors on /experity/map

## Error Identified

From Aptible logs (December 26, 2025):

```
TypeError: ClientSession._request() got an unexpected keyword argument 'seed'
  File "/usr/local/lib/python3.11/site-packages/azure/core/pipeline/transport/_aiohttp.py", line 346, in send
```

## Root Cause

**Version Compatibility Issue** between:
- Azure SDK (`azure-ai-agents`, `azure-core`)
- `aiohttp` library

The Azure SDK is trying to pass a `seed` parameter to `aiohttp.ClientSession._request()`, but:
1. The `seed` parameter may not be supported in the installed version of aiohttp
2. OR there's a bug/incompatibility in how Azure SDK uses this parameter
3. OR the Azure SDK version is too new/old for the aiohttp version

## Current Requirements

From `requirements.txt`:
- `aiohttp>=3.9.0`
- `azure-ai-agents>=1.0.0`
- `azure-ai-projects>=1.0.0`
- `azure-identity>=1.15.0`

## Impact

- **All requests to `/experity/map` fail** with 504/502 errors
- The error occurs when Azure SDK tries to make HTTP requests to Azure AI service
- This prevents any encounter mapping from working

## Solution Options

### Option 1: Pin Compatible Versions (Recommended)

Pin specific versions that are known to work together:

```txt
aiohttp==3.9.1
azure-core>=1.30.0,<2.0.0
azure-ai-agents>=1.0.0,<2.0.0
azure-ai-projects>=1.0.0,<2.0.0
```

### Option 2: Upgrade aiohttp

The `seed` parameter was added in aiohttp 3.9.0, but there might be issues. Try:
- `aiohttp>=3.10.0` (newer version with better support)

### Option 3: Downgrade Azure SDK

If the Azure SDK version is too new, try:
- `azure-ai-agents==1.0.0` (pin to specific version)
- `azure-core==1.30.0` (pin to specific version)

### Option 4: Use httpx Instead (Alternative)

If aiohttp continues to have issues, the Azure SDK might support httpx as an alternative transport. However, this would require code changes.

## Recommended Fix

1. **Update requirements.txt** with pinned versions
2. **Test locally** to ensure compatibility
3. **Deploy to Aptible** and verify the fix

## Testing After Fix

Run the test script to verify:
```bash
python3 test_experity_map_endpoint.py
```

Expected result: Requests should complete successfully (200) instead of timing out (504) or getting 502 errors.

