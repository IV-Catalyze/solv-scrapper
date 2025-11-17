# Quick Start: API-Only Mode (No Database Required)

Run the patient form monitor without installing PostgreSQL!

## Option 1: Automated Setup (Recommended)

Run the setup script:

```bash
./setup-api-only.sh
```

This will:
1. Ask for your API endpoint URL
2. Ask for Solvhealth queue URL (or use default)
3. Ask for API token (optional)
4. Create a `.env` file with all necessary settings

Then run:
```bash
python3 run_all.py
```

## Option 2: Manual Setup

1. **Create a `.env` file** in the project root:

```bash
# Required: Your API endpoint
API_URL=https://your-api-endpoint.com

# Required: Solvhealth queue URL
SOLVHEALTH_QUEUE_URL=https://manage.solvhealth.com/queue?location_ids=AXjwbE

# Disable database (API-only mode)
USE_DATABASE=false

# Enable API sending
USE_API=true
```

2. **Run the project:**

```bash
python3 run_all.py
```

## What Happens

When you run `python3 run_all.py` in API-only mode:

1. ✅ **No database startup** - PostgreSQL is not required
2. ✅ **No local API server** - Monitor sends directly to your external API
3. ✅ **Monitor starts** - Watches for patient form submissions
4. ✅ **Data sent to API** - Patient data is sent to `{API_URL}/patients/create`

## Environment Variables

### Required

- **`API_URL`**: Your external API endpoint (e.g., `https://app.example.com`)
- **`SOLVHEALTH_QUEUE_URL`**: Solvhealth queue page URL to monitor

### Optional

- **`USE_DATABASE`**: Set to `false` to disable database (default: `true`)
- **`USE_API`**: Set to `true` to enable API sending (default: `true`)
- **`API_TOKEN`**: API authentication token (if your API requires it)
- **`PLAYWRIGHT_HEADLESS`**: Set to `true` to run browser in background (default: `true`)

## Example .env File

```env
# API Configuration
API_URL=https://app-97926.on-aptible.com
API_TOKEN=your-token-here

# Solvhealth Configuration
SOLVHEALTH_QUEUE_URL=https://manage.solvhealth.com/queue?location_ids=AXjwbE

# API-Only Mode
USE_DATABASE=false
USE_API=true
PLAYWRIGHT_HEADLESS=true
```

## Troubleshooting

### "API_URL not set" Error

Make sure you've set `API_URL` in your `.env` file or environment:
```bash
export API_URL="https://your-api-endpoint.com"
```

### "Database connection error" Error

If you see database errors, make sure `USE_DATABASE=false` is set in your `.env` file.

### Monitor Not Sending Data

1. Check that `API_URL` is set correctly
2. Check that `USE_API=true` (or not set, defaults to true)
3. Check your API endpoint is accessible
4. Check API logs for any authentication errors

## Next Steps

- See [API_ONLY_MODE.md](API_ONLY_MODE.md) for detailed documentation
- See [README.md](README.md) for full project documentation

