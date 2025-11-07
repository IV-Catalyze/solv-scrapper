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
    
    # Check for SOLVHEALTH_QUEUE_URL
    if not os.getenv('SOLVHEALTH_QUEUE_URL'):
        errors.append("SOLVHEALTH_QUEUE_URL environment variable is not set")
    
    # Check if required files exist
    if not Path('api.py').exists():
        errors.append("api.py not found")
    
    if not Path('monitor_patient_form.py').exists():
        errors.append("monitor_patient_form.py not found")
    
    if errors:
        print_error("Missing requirements:")
        for error in errors:
            print_error(f"  - {error}")
        print()
        print_info("Please set SOLVHEALTH_QUEUE_URL, e.g.:")
        print_info("  export SOLVHEALTH_QUEUE_URL='https://manage.solvhealth.com/queue'")
        print_info("  or")
        print_info("  export SOLVHEALTH_QUEUE_URL='https://manage.solvhealth.com/queue?location_ids=AXjwbE'")
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
                        capture_output=True,
                        text=True,
                        stderr=subprocess.DEVNULL
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


def wait_for_database(host: str = 'localhost', port: int = 5432, timeout: int = 30):
    """Wait for database to be ready."""
    print_db(f"Waiting for database to be ready on {host}:{port}...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        if is_database_running(host, port):
            print_db("Database is ready!")
            time.sleep(1)  # Give it a moment to fully initialize
            return True
        time.sleep(0.5)
    
    print_error(f"Database did not become ready within {timeout} seconds")
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
    
    # Start database first (required for API)
    print_info("Starting services...")
    print()
    
    if not start_database():
        print_error("Failed to start database. API server requires database connection.")
        print_error("Please start PostgreSQL manually and try again.")
        sys.exit(1)
    
    print()
    
    # Start API server as subprocess
    api_process = None
    api_stream_thread = None
    api_port = None

    max_port_attempts = 20
    for attempt in range(max_port_attempts):
        candidate_port = api_port_preference + attempt

        if attempt > 0:
            print_warning(f"Retrying API server on port {candidate_port}...")

        print_api(f"Starting API server on {api_host}:{candidate_port}...")
        api_cmd = [
            sys.executable, '-m', 'uvicorn',
            'api:app',
            '--host', api_host,
            '--port', str(candidate_port),
            '--log-level', 'info'
        ]

        process = subprocess.Popen(
            api_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
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
    monitor_cmd = [sys.executable, 'monitor_patient_form.py']
    
    monitor_process = subprocess.Popen(
        monitor_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    # Stream monitor output
    monitor_stream_thread = stream_output(monitor_process, print_monitor, "Monitor")
    print_monitor(f"Monitor started (PID: {monitor_process.pid})")
    
    print()
    print("=" * 70)
    print_info("All services are running!")
    print()
    print_db(f"🗄️  Database: {os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}")
    print_info(f"📡 API Server: http://localhost:{api_port}")
    print_info(f"📡 API Docs: http://localhost:{api_port}/docs")
    print_info(f"🔍 Monitor: Watching for patient form submissions")
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

