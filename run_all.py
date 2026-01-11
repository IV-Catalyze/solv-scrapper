#!/usr/bin/env python3
"""
Run both the patient form monitor and API server simultaneously.

This script starts:
1. PostgreSQL database (if not already running)
2. The FastAPI server (api.py) to serve patient data
3. The patient form monitor (monitor_patient_form.py) to capture data

All processes run concurrently and can be stopped with Ctrl+C.
"""

import os
import sys
import time
import signal
import subprocess
import threading
from pathlib import Path
from typing import Optional

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

# Color codes for terminal output
class Colors:
    API = '\033[94m'      # Blue
    MONITOR = '\033[92m'  # Green
    DB = '\033[96m'       # Cyan
    ERROR = '\033[91m'    # Red
    WARNING = '\033[93m'  # Yellow
    RESET = '\033[0m'     # Reset
    BOLD = '\033[1m'      # Bold


def print_api(message: str):
    """Print message with API prefix."""
    print(f"{Colors.API}[API]{Colors.RESET} {message}")


def print_monitor(message: str):
    """Print message with Monitor prefix."""
    print(f"{Colors.MONITOR}[MONITOR]{Colors.RESET} {message}")


def print_error(message: str):
    """Print error message."""
    print(f"{Colors.ERROR}[ERROR]{Colors.RESET} {message}")


def print_info(message: str):
    """Print info message."""
    print(f"{Colors.BOLD}[INFO]{Colors.RESET} {message}")


def print_db(message: str):
    """Print message with DB prefix."""
    print(f"{Colors.DB}[DATABASE]{Colors.RESET} {message}")


def print_warning(message: str):
    """Print warning message."""
    print(f"{Colors.WARNING}[WARNING]{Colors.RESET} {message}")


def check_requirements():
    """Check if required environment variables and files exist."""
    errors = []
    
    # Set default SOLVHEALTH_QUEUE_URL if not provided
    if not os.getenv('SOLVHEALTH_QUEUE_URL'):
        default_url = 'https://manage.solvhealth.com/queue?location_ids=AXjwbE'
        os.environ['SOLVHEALTH_QUEUE_URL'] = default_url
        print_warning(f"SOLVHEALTH_QUEUE_URL not set, using default: {default_url}")
        print_warning("You can override this by setting SOLVHEALTH_QUEUE_URL environment variable")
        print()
    
    # Check if required files exist
    if not Path('app/api/routes.py').exists():
        errors.append("app/api/routes.py not found")
    
    if not Path('app/core/monitor.py').exists():
        errors.append("app/core/monitor.py not found")
    
    if errors:
        print_error("Missing requirements:")
        for error in errors:
            print_error(f"  - {error}")
        return False
    
    return True


def is_database_running(host: str = 'localhost', port: int = 5432):
    """Check if PostgreSQL database is running."""
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def start_database():
    """Start PostgreSQL database if not running."""
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = int(os.getenv('DB_PORT', '5432'))
    
    disable_autostart = os.getenv('RUN_ALL_AUTOSTART_DB', '1').strip().lower() in {'0', 'false', 'no', 'off'}
    if disable_autostart:
        print_db("Automatic database startup disabled via RUN_ALL_AUTOSTART_DB")
        if is_database_running(db_host, db_port):
            print_db(f"Database is already running on {db_host}:{db_port}")
            return True
        print_warning(
            "Database auto-start is disabled and no database is reachable. "
            "Please ensure your database is running before invoking run_all.py"
        )
        return False
    
    # Check if database is already running
    if is_database_running(db_host, db_port):
        print_db(f"Database is already running on {db_host}:{db_port}")
        return True
    
    print_db("Database is not running. Attempting to start...")
    
    # Try to start via brew services (macOS)
    try:
        # Check if brew is available
        brew_check = subprocess.run(
            ['which', 'brew'],
            capture_output=True,
            text=True
        )
        
        if brew_check.returncode == 0:
            # Try to find PostgreSQL service name
            services = subprocess.run(
                ['brew', 'services', 'list'],
                capture_output=True,
                text=True
            )
            
            if services.returncode == 0:
                # Look for postgresql services
                for line in services.stdout.split('\n'):
                    if 'postgresql' in line.lower() and 'stopped' in line.lower():
                        # Extract service name (e.g., postgresql@15)
                        parts = line.split()
                        if parts:
                            service_name = parts[0]
                            print_db(f"Starting PostgreSQL service: {service_name}")
                            result = subprocess.run(
                                ['brew', 'services', 'start', service_name],
                                capture_output=True,
                                text=True
                            )
                            if result.returncode == 0:
                                print_db(f"Started {service_name}")
                                # Wait for database to be ready
                                return wait_for_database(db_host, db_port)
                            else:
                                print_warning(f"Failed to start {service_name}: {result.stderr}")
                
                # If no stopped service found, try common names
                for service_name in ['postgresql@15', 'postgresql@14', 'postgresql@13', 'postgresql']:
                    result = subprocess.run(
                        ['brew', 'services', 'start', service_name],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        text=True
                    )
                    if result.returncode == 0:
                        print_db(f"Started {service_name}")
                        return wait_for_database(db_host, db_port)
    except Exception as e:
        print_warning(f"Could not start database via brew: {e}")
    
    # Try Docker as fallback
    try:
        docker_check = subprocess.run(
            ['which', 'docker'],
            capture_output=True,
            text=True
        )
        
        if docker_check.returncode == 0:
            # Check if postgres container exists
            containers = subprocess.run(
                ['docker', 'ps', '-a', '--filter', 'name=postgres', '--format', '{{.Names}}'],
                capture_output=True,
                text=True
            )
            
            if containers.stdout.strip():
                container_name = containers.stdout.strip().split('\n')[0]
                print_db(f"Starting Docker container: {container_name}")
                result = subprocess.run(
                    ['docker', 'start', container_name],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    print_db(f"Started {container_name}")
                    return wait_for_database(db_host, db_port)
    except Exception as e:
        print_warning(f"Could not start database via Docker: {e}")
    
    print_error("Could not automatically start database.")
    print_error("Please start PostgreSQL manually:")
    print_error("  - macOS: brew services start postgresql@15")
    print_error("  - Docker: docker start <container_name>")
    print_error("  - Or start PostgreSQL service manually")
    return False


def wait_for_database(host: str = 'localhost', port: int = 5432, timeout: int = 30, try_alternate_ports: bool = True):
    """Wait for database to be ready. If configured port fails, tries common alternate ports."""
    ports_to_try = [port]
    
    # If configured port fails and we should try alternates, add common PostgreSQL ports
    if try_alternate_ports:
        common_ports = [5432, 5433, 5434]
        for common_port in common_ports:
            if common_port not in ports_to_try:
                ports_to_try.append(common_port)
    
    print_db(f"Waiting for database to be ready on {host} (trying ports: {', '.join(map(str, ports_to_try))})...")
    start_time = time.time()
    
    # Try all ports in round-robin fashion until one succeeds or timeout
    while time.time() - start_time < timeout:
        for attempt_port in ports_to_try:
            if is_database_running(host, attempt_port):
                print_db(f"Database is ready on {host}:{attempt_port}!")
                time.sleep(1)  # Give it a moment to fully initialize
                # Update environment if we found a different port
                if attempt_port != port:
                    print_warning(f"Database found on port {attempt_port} instead of configured port {port}")
                    print_warning(f"Consider setting DB_PORT={attempt_port} in your .env file")
                    os.environ['DB_PORT'] = str(attempt_port)
                return True
            # Small delay between port checks
            time.sleep(0.2)
    
    print_error(f"Database did not become ready within {timeout} seconds on any of the tried ports: {ports_to_try}")
    return False


def wait_for_api(host: str = 'localhost', port: int = 8000, timeout: int = 30):
    """Wait for API server to be ready."""
    import socket
    import time
    
    print_info(f"Waiting for API server to start on {host}:{port}...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result == 0:
                print_info("API server is ready!")
                time.sleep(1)  # Give it a moment to fully initialize
                return True
        except Exception:
            pass
        
        time.sleep(0.5)
    
    print_error(f"API server did not start within {timeout} seconds")
    return False


def stream_output(process, prefix_func, process_name):
    """Stream output from a process with prefix."""
    import threading
    
    def stream():
        try:
            for line in iter(process.stdout.readline, ''):
                if line:
                    prefix_func(line.rstrip())
        except Exception as e:
            print_error(f"Error streaming {process_name} output: {e}")
    
    thread = threading.Thread(target=stream, daemon=True)
    thread.start()
    return thread


def main():
    """Main function to run both processes."""
    # Check requirements
    if not check_requirements():
        sys.exit(1)
    
    # Get configuration
    api_host = os.getenv('API_HOST', '0.0.0.0')
    api_port_preference = int(os.getenv('API_PORT', '8000'))
    wait_for_api_ready = os.getenv('WAIT_FOR_API', 'true').lower() == 'true'
    
    # Process management
    api_process = None
    monitor_process = None
    
    def signal_handler(sig, frame):
        """Handle Ctrl+C gracefully."""
        print()
        print_info("Shutting down...")
        
        if monitor_process:
            print_monitor("Stopping monitor...")
            monitor_process.terminate()
            try:
                monitor_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                monitor_process.kill()
        
        if api_process:
            print_api("Stopping API server...")
            api_process.terminate()
            try:
                api_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                api_process.kill()
        
        print_info("Shutdown complete. Goodbye!")
        sys.exit(0)
    
    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Print header
    print()
    print("=" * 70)
    print(f"{Colors.BOLD}🏥 Patient Form Monitor + API Server{Colors.RESET}")
    print("=" * 70)
    print()
    
    # Load and check configuration BEFORE any database operations
    # Force reload environment variables to ensure .env is read
    env_file_exists = Path('.env').exists()
    try:
        if env_file_exists:
            result = load_dotenv(override=True)
            if result:
                print_info(f"✅ Loaded environment variables from .env file")
            else:
                print_warning(f"⚠️  .env file exists but no variables were loaded")
        else:
            print_warning(f"⚠️  .env file not found - using environment defaults")
    except Exception as e:
        print_warning(f"⚠️  Could not reload .env file: {e}")
    
    # Read environment variables with explicit fallbacks
    # IMPORTANT: On Windows, make sure to strip whitespace and handle case sensitivity
    use_database_env = os.getenv('USE_DATABASE', 'true').strip().lower()
    use_database = use_database_env in {'1', 'true', 'yes', 'on'}
    api_url_env = os.getenv('API_URL', '').strip()
    
    # Determine if we need local API (only if no external API_URL set or it's localhost)
    use_local_api = not api_url_env or api_url_env == '' or 'localhost' in api_url_env.lower() or '127.0.0.1' in api_url_env
    
    print_info("Starting services...")
    print_info(f"Configuration check:")
    print_info(f"  .env file exists: {env_file_exists}")
    print_info(f"  USE_DATABASE={repr(use_database_env)} -> {use_database}")
    print_info(f"  API_URL={repr(api_url_env) or 'Not set (will use local API)'}")
    print_info(f"  Use local API: {use_local_api}")
    print()
    
    # CRITICAL: Skip ALL database operations if USE_DATABASE=false
    # Check this FIRST and set flags to prevent any database startup
    skip_database = not use_database
    
    if skip_database:
        print_info("📡 Database disabled (USE_DATABASE=false) - Running in API-only mode")
        print_info("   ✅ Skipping all database startup and checks")
        print_info("   ✅ Monitor will send data directly to external API")
        print()
        # Explicitly prevent any database operations
        use_database = False
        use_local_api = False
    elif not use_local_api:
        print_info("📡 Using external API endpoint - Database not required for monitor")
        print()
    
    # Start database ONLY if explicitly needed (database enabled AND using local API server)
    # This check should now NEVER pass when USE_DATABASE=false due to skip_database flag
    if not skip_database and use_database and use_local_api:
        print_info("⚠️  Attempting to start database (database mode)...")
        if not start_database():
            print_error("Failed to start database. Local API server requires database connection.")
            print_error("Please start PostgreSQL manually and try again.")
            print_error("Or set USE_DATABASE=false and API_URL to an external endpoint for API-only mode.")
            sys.exit(1)
        print()
    else:
        # Explicitly skip database startup - this is the safe path
        if skip_database:
            print_info("✅ Database startup skipped (API-only mode)")
        elif not use_local_api:
            print_info("✅ Database startup skipped (using external API)")
        print()
    
    # Start API server as subprocess (only if using local API)
    api_process = None
    api_stream_thread = None
    api_port = None
    
    if not use_local_api:
        print_info("📡 External API_URL configured - Skipping local API server")
        print_info(f"   Monitor will send data to: {api_url_env}")
        api_port = None  # No local API server
    else:
        # Start local API server
        max_port_attempts = 20
        for attempt in range(max_port_attempts):
            candidate_port = api_port_preference + attempt

            if attempt > 0:
                print_warning(f"Retrying API server on port {candidate_port}...")

            print_api(f"Starting API server on {api_host}:{candidate_port}...")
            api_cmd = [
                sys.executable, '-m', 'uvicorn',
                'app.api.routes:app',
                '--host', api_host,
                '--port', str(candidate_port),
                '--log-level', 'info'
            ]

            # Ensure environment variables are passed to subprocess
            api_env = os.environ.copy()

            process = subprocess.Popen(
                api_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env=api_env
            )

            time.sleep(0.6)

            if process.poll() is not None:
                output = process.stdout.read() if process.stdout else ''
                output_lower = output.lower() if output else ''
                if 'address already in use' in output_lower:
                    print_warning(
                        f"Port {candidate_port} is already in use. Trying next available port."
                    )
                    if output:
                        for line in output.strip().splitlines():
                            print_api(line)
                    continue
                else:
                    if output:
                        for line in output.strip().splitlines():
                            print_api(line)
                    print_error("API server exited during startup. Please check logs above.")
                    sys.exit(1)

            # Success
            api_process = process
            api_port = candidate_port
            break

        if not api_process or api_port is None:
            print_error(
                f"Unable to start API server after {max_port_attempts} attempts."
            )
            print_error("Please free a port or set API_PORT to an available value.")
            sys.exit(1)

        # Stream API output
        api_stream_thread = stream_output(api_process, print_api, "API")
        print_api(f"API server started (PID: {api_process.pid})")

        # Wait for API to be ready (optional)
        if wait_for_api_ready:
            if not wait_for_api('localhost', api_port):
                print_error("Failed to start API server")
                if api_process:
                    api_process.terminate()
                sys.exit(1)
        else:
            print_info("Waiting 3 seconds for API server to initialize...")
            time.sleep(3)
    
    print()
    
    # Start monitor as subprocess
    print_monitor("Starting patient form monitor...")
    monitor_cmd = [sys.executable, '-m', 'app.core.monitor']
    
    # Ensure environment variables are passed to subprocess
    monitor_env = os.environ.copy()
    
    # Explicitly pass API_URL if it's set (for production)
    api_url_env = os.getenv('API_URL')
    if api_url_env:
        monitor_env['API_URL'] = api_url_env
        print_monitor(f"📡 API_URL configured: {api_url_env} (will send to production)")
    else:
        # Only set API_PORT if API_URL is not set (for local development)
        # If API_URL is set, it takes precedence and API_PORT will be ignored
        if api_port:
            monitor_env['API_PORT'] = str(api_port)
            print_monitor(f"📡 Using localhost API on port {api_port}")
        else:
            print_warning("⚠️  No API_URL or local API server - monitor may not be able to send data")
    
    # Pass USE_DATABASE to monitor
    if 'USE_DATABASE' in os.environ:
        monitor_env['USE_DATABASE'] = os.environ['USE_DATABASE']
    
    monitor_process = subprocess.Popen(
        monitor_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
        env=monitor_env
    )
    
    # Stream monitor output
    monitor_stream_thread = stream_output(monitor_process, print_monitor, "Monitor")
    print_monitor(f"Monitor started (PID: {monitor_process.pid})")
    
    print()
    print("=" * 70)
    print_info("All services are running!")
    print()
    if use_database and use_local_api:
        print_db(f"🗄️  Database: {os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}")
    if use_local_api and api_port:
        print_info(f"📡 API Server: http://localhost:{api_port}")
        print_info(f"📡 API Docs: http://localhost:{api_port}/docs")
    else:
        print_info(f"📡 External API: {api_url_env}")
    print_info(f"🔍 Monitor: Watching for patient form submissions")
    if not use_database:
        print_info(f"💡 Mode: API-only (database disabled)")
    print()
    print_info("Press Ctrl+C to stop all services")
    print("=" * 70)
    print()
    
    # Monitor both processes
    try:
        while True:
            # Check if processes are still alive
            if api_process and api_process.poll() is not None:
                print_error("API server process died unexpectedly")
                if monitor_process:
                    monitor_process.terminate()
                sys.exit(1)
            
            if monitor_process and monitor_process.poll() is not None:
                print_error("Monitor process died unexpectedly")
                if api_process:
                    api_process.terminate()
                sys.exit(1)
            
            time.sleep(1)
    
    except KeyboardInterrupt:
        signal_handler(None, None)


if __name__ == '__main__':
    main()

