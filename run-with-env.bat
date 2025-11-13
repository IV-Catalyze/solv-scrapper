@echo off
REM Batch file to run monitor with environment variables set
REM This ensures .env file works on Windows

REM Set environment variables
set API_URL=https://app-97926.on-aptible.com
set SOLVHEALTH_QUEUE_URL=https://manage.solvhealth.com/queue?location_ids=AXjwbE
set USE_DATABASE=false
set USE_API=true
set PLAYWRIGHT_HEADLESS=false

REM Run the monitor
python3 monitor_patient_form.py

pause

