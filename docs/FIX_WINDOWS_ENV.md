# Quick Fix for Windows .env File Issues

On Windows, the `.env` file needs to be in a specific location and format. Here's how to fix it:

## Step 1: Check if .env file exists

In PowerShell, navigate to your project folder and check:
```powershell
cd C:\Users\exercatalyze\Desktop\solv-scrapper
dir .env
```

## Step 2: Create/Update .env file

Create a `.env` file in the project root (same folder as `monitor_patient_form.py`) with this content:

```
API_URL=https://app-97926.on-aptible.com
SOLVHEALTH_QUEUE_URL=https://manage.solvhealth.com/queue?location_ids=AXjwbE
USE_DATABASE=false
USE_API=true
PLAYWRIGHT_HEADLESS=false
```

**Important Notes:**
- No spaces around the `=` sign
- No quotes around values (or use quotes consistently)
- No `export` keyword (Windows doesn't need it)
- Save as `.env` (not `.env.txt`)

## Step 3: Install Missing Packages

```powershell
python3 -m pip install httpx playwright
python3 -m playwright install chromium
```

## Step 4: Verify .env is Working

Run this test:
```powershell
python3 -c "import os; from dotenv import load_dotenv; load_dotenv(); print('API_URL:', os.getenv('API_URL')); print('SOLVHEALTH_QUEUE_URL:', os.getenv('SOLVHEALTH_QUEUE_URL'))"
```

You should see your values printed.

## Step 5: Run the Monitor

```powershell
python3 monitor_patient_form.py
```

## Troubleshooting

### If .env still not working:

1. **Check file location**: Make sure `.env` is in the same folder as `monitor_patient_form.py`

2. **Check file encoding**: Save as UTF-8 (not UTF-16 or other encodings)

3. **Check file extension**: Make sure it's `.env` not `.env.txt`
   - In Windows Explorer, enable "Show file name extensions"
   - If you see `.env.txt`, rename to `.env`

4. **Manual environment variables** (temporary fix):
   ```powershell
   $env:API_URL="https://app-97926.on-aptible.com"
   $env:SOLVHEALTH_QUEUE_URL="https://manage.solvhealth.com/queue?location_ids=AXjwbE"
   $env:USE_DATABASE="false"
   python3 monitor_patient_form.py
   ```

