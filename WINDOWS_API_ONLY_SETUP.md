# Windows Setup Guide - API-Only Mode (No Database Required)

Complete step-by-step guide to setup and run the patient form monitor on a **new Windows PC** in API-only mode (no PostgreSQL installation needed).

## Prerequisites

- Windows 10 or later
- Internet connection
- Administrator access (for installation)

## Step-by-Step Setup

### Step 1: Install Python

1. **Download Python:**
   - Go to https://www.python.org/downloads/
   - Click "Download Python" (latest version, e.g., Python 3.11 or 3.12)

2. **Install Python:**
   - Run the downloaded installer
   - ⚠️ **IMPORTANT:** Check the box **"Add Python to PATH"** at the bottom
   - Click "Install Now"
   - Wait for installation to complete
   - Click "Close"

3. **Verify Python Installation:**
   - Open **Command Prompt** (search "cmd" in Start menu)
   - Type:
     ```cmd
     python --version
     ```
   - You should see: `Python 3.x.x`
   - Type:
     ```cmd
     pip --version
     ```
   - You should see: `pip 2x.x`

### Step 2: Install Git (Optional but Recommended)

1. **Download Git:**
   - Go to https://git-scm.com/download/win
   - Download the installer

2. **Install Git:**
   - Run the installer
   - Click "Next" through all steps (defaults are fine)
   - Click "Install"
   - Click "Finish"

### Step 3: Get the Project Files

**Option A: Using Git (Recommended)**
```cmd
cd Desktop
git clone <your-repo-url>
cd solv-scrapper-clone
```

**Option B: Manual Download**
1. Download the project as a ZIP file
2. Extract it to `Desktop\solv-scrapper-clone`
3. Open Command Prompt and navigate:
   ```cmd
   cd Desktop\solv-scrapper-clone
   ```

### Step 4: Install Python Dependencies

1. **Open Command Prompt** in the project folder:
   - Navigate to the project folder in File Explorer
   - Click in the address bar, type `cmd`, press Enter
   - Or: Right-click in the folder → "Open in Terminal"

2. **Install dependencies:**
   ```cmd
   pip install -r requirements.txt
   ```

3. **Install Playwright browsers:**
   ```cmd
   playwright install chromium
   ```

   ⚠️ **Wait for installation to complete** (this may take a few minutes)

### Step 5: Configure Environment Variables

1. **Create `.env` file** in the project folder:
   - Create a new text file named `.env` (note the dot at the beginning)
   - ⚠️ **Important:** In Windows Explorer, you may need to enable "Show file name extensions" and "Show hidden files"
   - Or use Command Prompt:
     ```cmd
     notepad .env
     ```

2. **Add your configuration** to `.env`:
   ```env
   # Your API endpoint (REQUIRED)
   API_URL=https://your-api-endpoint.com
   
   # Solvhealth queue URL (REQUIRED)
   SOLVHEALTH_QUEUE_URL=https://manage.solvhealth.com/queue?location_ids=AXjwbE
   
   # Disable database (API-only mode)
   USE_DATABASE=false
   
   # Enable API sending
   USE_API=true
   
   # Run browser in background
   PLAYWRIGHT_HEADLESS=true
   ```

3. **Replace `API_URL`** with your actual API endpoint:
   - Example: `API_URL=https://app-97926.on-aptible.com`

4. **Save the file** (Ctrl+S) and close Notepad

### Step 6: Run the Project

**In Command Prompt**, run:
```cmd
python run_all.py
```

Or:
```cmd
python3 run_all.py
```

## What Happens When You Run

1. ✅ **No database required** - PostgreSQL is not needed
2. ✅ **Monitor starts** - Browser opens (or runs in background if headless)
3. ✅ **Waits for forms** - Automatically captures patient form submissions
4. ✅ **Sends to API** - Patient data is sent to your `API_URL/patients/create`

## Troubleshooting

### "python is not recognized"

**Solution:**
1. Reinstall Python and make sure **"Add Python to PATH"** is checked
2. Or manually add Python to PATH:
   - Search "Environment Variables" in Start menu
   - Click "Edit the system environment variables"
   - Click "Environment Variables"
   - Under "System variables", find "Path" and click "Edit"
   - Click "New" and add: `C:\Python3x` (replace x with your version)
   - Click "OK" on all dialogs
   - **Restart Command Prompt**

### "pip is not recognized"

**Solution:**
1. Make sure Python is installed correctly
2. Try: `python -m pip install -r requirements.txt`
3. If that fails, reinstall Python with "Add to PATH" checked

### "playwright install" fails

**Solution:**
1. Make sure you have internet connection
2. Try running as Administrator:
   - Right-click Command Prompt → "Run as administrator"
   - Navigate to project folder
   - Run `playwright install chromium` again

### Browser doesn't open / "Playwright not found"

**Solution:**
1. Make sure Playwright browsers are installed:
   ```cmd
   playwright install chromium
   ```
2. If using headless mode, browser runs in background (this is normal)

### "API_URL not set" error

**Solution:**
1. Make sure `.env` file exists in the project folder
2. Check that `API_URL` is set in `.env` file
3. Make sure there are no spaces around the `=` sign
4. Make sure there are no quotes unless needed (Windows may auto-add quotes)

### "ModuleNotFoundError" or "No module named..."

**Solution:**
1. Make sure you installed requirements:
   ```cmd
   pip install -r requirements.txt
   ```
2. If that fails, try:
   ```cmd
   python -m pip install -r requirements.txt
   ```

### Project files not found

**Solution:**
1. Make sure you're in the correct folder
2. Check your current directory:
   ```cmd
   cd
   dir
   ```
3. Navigate to the project:
   ```cmd
   cd Desktop\solv-scrapper-clone
   ```
   (Adjust path based on where you extracted the project)

## Running Every Time

To run the project each time:

1. **Open Command Prompt**
2. **Navigate to project folder:**
   ```cmd
   cd Desktop\solv-scrapper-clone
   ```
   (Adjust path as needed)

3. **Run:**
   ```cmd
   python run_all.py
   ```

## Optional: Create a Desktop Shortcut

1. **Create a batch file:**
   - Create a new text file named `run.bat` in the project folder
   - Add this content:
     ```bat
     @echo off
     cd /d "%~dp0"
     python run_all.py
     pause
     ```
   - Save and close

2. **Create shortcut:**
   - Right-click `run.bat` → "Create shortcut"
   - Drag the shortcut to Desktop
   - Double-click to run anytime!

## Configuration Options

### Show Browser Window

If you want to see the browser window (for debugging), edit `.env`:
```env
PLAYWRIGHT_HEADLESS=false
```

### Change API Endpoint

Edit `.env` and change:
```env
API_URL=https://your-new-endpoint.com
```

### Add API Authentication

If your API requires authentication, add to `.env`:
```env
API_TOKEN=your-api-token-here
```

## What Gets Sent to Your API

When a patient form is submitted:

- **Endpoint:** `POST {API_URL}/patients/create`
- **Format:** JSON
- **Data includes:**
  - Patient name (first/last)
  - Date of birth
  - Mobile phone
  - Sex at birth
  - Reason for visit
  - EMR ID
  - Location information
  - Booking information

## Quick Reference Commands

```cmd
# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Run the project
python run_all.py

# Check Python version
python --version

# Check current directory
cd

# List files
dir
```

## Next Steps

- See [API_ONLY_MODE.md](API_ONLY_MODE.md) for detailed API configuration
- See [README.md](README.md) for full project documentation

## Need Help?

Common issues:
1. **Python not in PATH** - Reinstall Python with "Add to PATH" checked
2. **Missing dependencies** - Run `pip install -r requirements.txt`
3. **Playwright browsers not installed** - Run `playwright install chromium`
4. **API_URL not set** - Check `.env` file exists and has correct format

---

**That's it!** You're ready to capture patient data and send it to your API! 🎉

