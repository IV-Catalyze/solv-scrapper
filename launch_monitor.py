#!/usr/bin/env python3
"""
Launcher script for the patient monitor that ensures .env file is loaded.
This script explicitly loads the .env file before running the monitor.
"""

import os
import sys
from pathlib import Path

# Get the directory where this script is located (project root)
# Define these before try block so they're available in error messages
script_dir = Path(__file__).parent.absolute()
env_path = script_dir / '.env'

# Try to load .env file
dotenv_available = True
try:
    from dotenv import load_dotenv
    
    print(f"Looking for .env file at: {env_path}")
    
    if env_path.exists():
        print(f"✅ Found .env file at: {env_path}")
        # Load with override=True to ensure variables are set
        result = load_dotenv(dotenv_path=env_path, override=True)
        if result:
            print("✅ Successfully loaded .env file")
        else:
            print("⚠️  .env file exists but no variables were loaded")
    else:
        print(f"❌ .env file not found at: {env_path}")
        print(f"   Current working directory: {os.getcwd()}")
        print(f"   Script directory: {script_dir}")
        print("\nPlease create a .env file in the project root with:")
        print("  API_URL=https://app-97926.on-aptible.com")
        print("  SOLVHEALTH_QUEUE_URL=https://manage.solvhealth.com/queue")
        sys.exit(1)
        
except ImportError:
    dotenv_available = False
    print("⚠️  python-dotenv not installed. Install with: pip install python-dotenv")
    print("   Attempting to read .env file manually...")
    
    # Manual .env file reading as fallback
    if env_path.exists():
        print(f"✅ Found .env file at: {env_path}")
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        os.environ[key] = value
            print("✅ Successfully loaded .env file (manual method)")
        except Exception as e:
            print(f"❌ Error reading .env file: {e}")
    else:
        print(f"❌ .env file not found at: {env_path}")
        print(f"   Current working directory: {os.getcwd()}")
        print(f"   Script directory: {script_dir}")
        print("\nPlease create a .env file in the project root with:")
        print("  API_URL=https://app-97926.on-aptible.com")
        print("  SOLVHEALTH_QUEUE_URL=https://manage.solvhealth.com/queue")
        sys.exit(1)

# Verify critical environment variables are set
api_url = os.getenv('API_URL')
queue_url = os.getenv('SOLVHEALTH_QUEUE_URL')

print("\n" + "="*60)
print("Environment Variables Check:")
print("="*60)
print(f"API_URL: {'✅ Set' if api_url else '❌ Not set'}")
if api_url:
    print(f"  Value: {api_url}")
print(f"SOLVHEALTH_QUEUE_URL: {'✅ Set' if queue_url else '❌ Not set'}")
if queue_url:
    print(f"  Value: {queue_url}")
print("="*60 + "\n")

if not api_url or not queue_url:
    print("❌ ERROR: Required environment variables are missing!")
    print("\nPlease ensure your .env file contains:")
    print("  API_URL=https://app-97926.on-aptible.com")
    print("  SOLVHEALTH_QUEUE_URL=https://manage.solvhealth.com/queue")
    print(f"\n.env file should be located at: {env_path}")
    sys.exit(1)

# Change to project directory to ensure relative imports work
os.chdir(script_dir)
print(f"Working directory: {os.getcwd()}\n")

# Now run the monitor
print("="*60)
print("Starting Patient Monitor...")
print("="*60 + "\n")

# Import and run the monitor
try:
    from app.core.monitor import main
    import asyncio
    asyncio.run(main())
except KeyboardInterrupt:
    print("\n\n🛑 Monitor stopped by user")
except Exception as e:
    print(f"\n❌ Error running monitor: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

