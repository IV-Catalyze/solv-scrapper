@echo off
REM ============================================
REM Run Patient Monitor
REM ============================================

REM Try to find the project directory
REM First, check if this script is in the project root
set SCRIPT_DIR=%~dp0
if exist "%SCRIPT_DIR%.env" (
    set PROJECT_DIR=%SCRIPT_DIR%
    goto :found_project
)

REM If not, try common project locations
REM Update this path to match your actual project location
set PROJECT_DIR=C:\Users\exercatalyze\Desktop\solv-scrapper
if exist "%PROJECT_DIR%\.env" (
    goto :found_project
)

REM Try alternative location
set PROJECT_DIR=C:\Users\exercatalyze\Documents\solv-scrapper-clone
if exist "%PROJECT_DIR%\.env" (
    goto :found_project
)

REM If still not found, use script directory and warn
set PROJECT_DIR=%SCRIPT_DIR%
echo WARNING: Could not find .env file automatically.
echo Using directory: %PROJECT_DIR%
echo.
goto :check_env

:found_project
cd /d "%PROJECT_DIR%"
echo Project directory: %CD%
echo.

:check_env
REM Check if .env file exists
if not exist ".env" (
    echo ============================================
    echo ERROR: .env file not found!
    echo ============================================
    echo.
    echo Please create a .env file in the project directory with:
    echo   API_URL=https://app-97926.on-aptible.com
    echo   SOLVHEALTH_QUEUE_URL=https://manage.solvhealth.com/queue
    echo.
    echo Current directory: %CD%
    echo.
    echo Press any key to exit...
    pause >nul
    exit /b 1
)

REM Display .env file location for debugging
echo .env file found at: %CD%\.env
echo.

REM Check if python-dotenv is installed
echo Checking for python-dotenv...
python3 -c "import dotenv" 2>nul
if errorlevel 1 (
    echo python-dotenv not found. Installing...
    python3 -m pip install python-dotenv
    if errorlevel 1 (
        echo WARNING: Failed to install python-dotenv
        echo The launcher will attempt to read .env file manually.
        echo.
    ) else (
        echo ✅ python-dotenv installed successfully
        echo.
    )
) else (
    echo ✅ python-dotenv is installed
    echo.
)

REM Run the monitor using the launcher script
echo ============================================
echo Starting Patient Monitor...
echo ============================================
echo.
python3 launch_monitor.py

REM Keep window open if there's an error
if errorlevel 1 (
    echo.
    echo ============================================
    echo Error occurred! Check the messages above.
    echo ============================================
    pause
)

