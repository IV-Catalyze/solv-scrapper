# Fix: aiohttp Compatibility Issue with Azure SDK

## Problem

The application is failing with:
```
TypeError: ClientSession._request() got an unexpected keyword argument 'seed'
```

This occurs when Azure SDK tries to make HTTP requests using aiohttp.

## Solution Applied

Updated `requirements.txt` to:
1. **Add explicit `azure-core` dependency** with version constraint
2. **Upgrade `aiohttp` to >=3.10.0** (better support for `seed` parameter)
3. **Add version constraints** to Azure SDK packages to prevent breaking changes

## Changes Made

```diff
- aiohttp>=3.9.0
+ aiohttp>=3.10.0,<4.0.0
+ azure-core>=1.30.0,<2.0.0
- azure-ai-agents>=1.0.0
- azure-ai-projects>=1.0.0
+ azure-ai-agents>=1.0.0,<2.0.0
+ azure-ai-projects>=1.0.0,<2.0.0
```

## Deployment Steps

1. **Update requirements.txt** (already done)
2. **Redeploy to Aptible**:
   ```bash
   git add requirements.txt
   git commit -m "Fix: Update aiohttp and Azure SDK versions for compatibility"
   aptible deploy --app solv-scrapper
   ```
3. **Verify the fix**:
   ```bash
   python3 test_experity_map_endpoint.py
   ```

## Expected Result

After deployment:
- ✅ No more `TypeError: ClientSession._request() got an unexpected keyword argument 'seed'`
- ✅ `/experity/map` endpoint should work correctly
- ✅ Requests should return 200 (success) instead of 504/502

## If Issue Persists

If the error continues after deployment:

1. **Check installed versions** in Aptible:
   ```bash
   aptible run --app solv-scrapper python -c "import aiohttp; import azure.core; print(f'aiohttp: {aiohttp.__version__}'); print(f'azure-core: {azure.core.__version__}')"
   ```

2. **Try pinning exact versions**:
   ```txt
   aiohttp==3.10.1
   azure-core==1.30.0
   azure-ai-agents==1.0.0
   ```

3. **Alternative: Use httpx transport** (requires code changes to Azure client)

## References

- Azure SDK documentation: https://github.com/Azure/azure-sdk-for-python
- aiohttp documentation: https://docs.aiohttp.org/
- Error location: `azure/core/pipeline/transport/_aiohttp.py:346`

