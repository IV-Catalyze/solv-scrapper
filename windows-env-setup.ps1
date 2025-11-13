# Windows Environment Setup Script
# Run this in PowerShell: .\windows-env-setup.ps1

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Windows Environment Setup" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if .env exists
if (Test-Path .env) {
    Write-Host "⚠️  .env file already exists" -ForegroundColor Yellow
    $overwrite = Read-Host "Do you want to overwrite it? (y/N)"
    if ($overwrite -ne "y") {
        Write-Host "Keeping existing .env file" -ForegroundColor Green
        exit
    }
}

Write-Host "Creating .env file..." -ForegroundColor Green

# Get API URL
$apiUrl = Read-Host "Enter your API endpoint URL (e.g., https://app-97926.on-aptible.com)"
if ([string]::IsNullOrWhiteSpace($apiUrl)) {
    Write-Host "❌ API URL is required" -ForegroundColor Red
    exit 1
}

# Get Queue URL
$queueUrl = Read-Host "Enter Solvhealth queue URL (press Enter for default)"
if ([string]::IsNullOrWhiteSpace($queueUrl)) {
    $queueUrl = "https://manage.solvhealth.com/queue?location_ids=AXjwbE"
}

# Create .env file
$envContent = @"
# Patient Form Monitor - API-Only Configuration

# Required: API endpoint URL
API_URL=$apiUrl

# Required: Solvhealth queue URL
SOLVHEALTH_QUEUE_URL=$queueUrl

# Disable database (API-only mode)
USE_DATABASE=false

# Enable API sending
USE_API=true

# Playwright headless mode (false = browser visible)
PLAYWRIGHT_HEADLESS=false
"@

$envContent | Out-File -FilePath .env -Encoding utf8 -NoNewline

Write-Host ""
Write-Host "✅ .env file created successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Installing required packages..." -ForegroundColor Cyan
python3 -m pip install httpx playwright --quiet

Write-Host ""
Write-Host "Installing Playwright browsers..." -ForegroundColor Cyan
python3 -m playwright install chromium

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "You can now run:" -ForegroundColor Yellow
Write-Host "  python3 monitor_patient_form.py" -ForegroundColor White
Write-Host "or" -ForegroundColor Yellow
Write-Host "  python3 run_all.py" -ForegroundColor White
Write-Host ""
