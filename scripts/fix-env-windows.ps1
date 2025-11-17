# Quick Fix for .env File on Windows
# Run this in PowerShell: .\fix-env-windows.ps1

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Fixing .env File on Windows" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if .env exists
if (Test-Path .env) {
    Write-Host "Found .env file" -ForegroundColor Green
    Write-Host ""
    Write-Host "Current contents:" -ForegroundColor Yellow
    Get-Content .env
    Write-Host ""
    
    $recreate = Read-Host "Do you want to recreate it? (y/N)"
    if ($recreate -ne "y") {
        Write-Host "Keeping existing file" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Testing if Python can read it..." -ForegroundColor Cyan
        python3 -c "import os; from dotenv import load_dotenv; load_dotenv(); print('API_URL:', os.getenv('API_URL')); print('SOLVHEALTH_QUEUE_URL:', os.getenv('SOLVHEALTH_QUEUE_URL'))"
        exit
    }
} else {
    Write-Host "No .env file found. Creating one..." -ForegroundColor Yellow
}

# Create .env file with proper Windows encoding
$envContent = @"
API_URL=https://app-97926.on-aptible.com
SOLVHEALTH_QUEUE_URL=https://manage.solvhealth.com/queue?location_ids=AXjwbE
USE_DATABASE=false
USE_API=true
PLAYWRIGHT_HEADLESS=false
"@

# Save with UTF-8 encoding (no BOM)
[System.IO.File]::WriteAllText((Resolve-Path .).Path + "\.env", $envContent, [System.Text.UTF8Encoding]::new($false))

Write-Host "✅ .env file created/updated!" -ForegroundColor Green
Write-Host ""

# Test if Python can read it
Write-Host "Testing if Python can read the .env file..." -ForegroundColor Cyan
python3 -c "import os; from dotenv import load_dotenv; result = load_dotenv(); print('load_dotenv returned:', result); print('API_URL:', repr(os.getenv('API_URL'))); print('SOLVHEALTH_QUEUE_URL:', repr(os.getenv('SOLVHEALTH_QUEUE_URL')))"

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "If values show as 'None', try this:" -ForegroundColor Yellow
Write-Host ""
Write-Host "Option 1: Set environment variables in PowerShell:" -ForegroundColor White
Write-Host '  $env:API_URL="https://app-97926.on-aptible.com"' -ForegroundColor Gray
Write-Host '  $env:SOLVHEALTH_QUEUE_URL="https://manage.solvhealth.com/queue?location_ids=AXjwbE"' -ForegroundColor Gray
Write-Host '  $env:USE_DATABASE="false"' -ForegroundColor Gray
Write-Host '  python3 -m app.core.monitor' -ForegroundColor Gray
Write-Host ""
Write-Host "Option 2: Create a .bat file with environment variables" -ForegroundColor White
Write-Host "==========================================" -ForegroundColor Green

