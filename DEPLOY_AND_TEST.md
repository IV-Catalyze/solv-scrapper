# Deploy Fix and Test Instructions

## Problem Summary
The `/experity/map` endpoint is failing with:
- **504 Gateway Timeout** errors
- **502 Bad Gateway** errors  
- **Root Cause**: `TypeError: ClientSession._request() got an unexpected keyword argument 'seed'`

This is a version compatibility issue between Azure SDK and aiohttp.

## Fix Applied
✅ Updated `requirements.txt` with compatible versions:
- `aiohttp>=3.10.0,<4.0.0` (upgraded from 3.9.0)
- `azure-core>=1.30.0,<2.0.0` (explicitly added)
- Version constraints on Azure SDK packages

## Deployment Steps

### Step 1: Commit and Push Changes
```bash
cd /Users/biruktsegaye/Documents/solv-scrapper-clone
git add requirements.txt
git commit -m "Fix: Update aiohttp and Azure SDK versions to resolve compatibility issue"
git push
```

### Step 2: Deploy to Aptible
```bash
aptible deploy --app solv-scrapper
```

### Step 3: Wait for Deployment
Wait 2-3 minutes for the deployment to complete. You can monitor with:
```bash
aptible logs --app solv-scrapper --follow
```

### Step 4: Verify Deployment
Check that new packages are installed:
```bash
aptible run --app solv-scrapper python -c "import aiohttp; import azure.core; print(f'aiohttp: {aiohttp.__version__}'); print(f'azure-core: {azure.core.__version__}')"
```

Expected output:
- `aiohttp: 3.10.x` (should be 3.10 or higher)
- `azure-core: 1.30.x` or higher

### Step 5: Run Test
```bash
cd /Users/biruktsegaye/Documents/solv-scrapper-clone
python3 test_experity_map_endpoint.py
```

## Expected Test Results After Fix

### Before Fix:
- ❌ All requests: HTTP 504 (Timeout) or HTTP 502 (Bad Gateway)
- ❌ Error: `TypeError: ClientSession._request() got an unexpected keyword argument 'seed'`

### After Fix:
- ✅ Format validation tests: HTTP 200 (Success)
- ✅ Requests complete in < 30 seconds
- ✅ Response includes `experityActions` with complaints, lab orders, ICD updates
- ✅ No TypeError errors in logs

## Quick Test Command
```bash
# Run a single quick test
python3 test_experity_map_endpoint.py --timeout 180 | head -50
```

## Troubleshooting

### If deployment fails:
1. Check Aptible logs: `aptible logs --app solv-scrapper`
2. Verify requirements.txt syntax is correct
3. Try deploying again: `aptible deploy --app solv-scrapper`

### If test still fails after deployment:
1. Check logs for new errors:
   ```bash
   aptible logs --app solv-scrapper | grep -i "error\|exception" | tail -20
   ```
2. Verify package versions are correct (see Step 4 above)
3. Check if Azure AI service is accessible

### If aiohttp version is still wrong:
Try pinning exact version in requirements.txt:
```txt
aiohttp==3.10.1
```

## Success Criteria
✅ Test script shows HTTP 200 responses  
✅ No TypeError about 'seed' parameter  
✅ Requests complete successfully  
✅ Response contains valid Experity mapping data

