#!/usr/bin/env python3
"""
Simple script to test the FastAPI patient endpoint.
"""

import requests
import sys
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API_BASE_URL = os.getenv('API_BASE_URL', 'http://localhost:8000')


def test_root_endpoint():
    """Test the root endpoint."""
    print("=" * 60)
    print("Testing root endpoint...")
    print("=" * 60)
    
    try:
        response = requests.get(f"{API_BASE_URL}/")
        response.raise_for_status()
        data = response.json()
        print("✅ Root endpoint is working!")
        print(f"   Message: {data.get('message')}")
        print(f"   Version: {data.get('version')}")
        print(f"   Available endpoints: {list(data.get('endpoints', {}).keys())}")
        return True
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API. Is the server running?")
        print(f"   Try: python api.py")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def get_emr_ids_from_db():
    """Get available EMR IDs from the database."""
    try:
        import psycopg2
        from dotenv import load_dotenv
        
        load_dotenv()
        
        # Check if DATABASE_URL is set (preferred for cloud deployments)
        database_url = os.getenv('DATABASE_URL')
        
        if database_url:
            # Parse the connection URL
            try:
                from urllib.parse import urlparse
                # Handle postgres:// and postgresql:// URLs
                if database_url.startswith('postgres://'):
                    database_url = database_url.replace('postgres://', 'postgresql://', 1)
                
                parsed = urlparse(database_url)
                
                db_config = {
                    'host': parsed.hostname,
                    'port': parsed.port or 5432,
                    'database': parsed.path.lstrip('/'),
                    'user': parsed.username,
                    'password': parsed.password or ''
                }
                # Enable SSL for remote databases (Aptible requires SSL)
                if parsed.hostname and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
                    db_config['sslmode'] = 'require'
            except Exception as e:
                print(f"Error parsing DATABASE_URL: {e}")
                return []
        else:
            # Fall back to individual environment variables
            db_host = os.getenv('DB_HOST', 'localhost')
            db_config = {
                'host': db_host,
                'port': os.getenv('DB_PORT', '5432'),
                'database': os.getenv('DB_NAME', 'solvhealth_patients'),
                'user': os.getenv('DB_USER', 'postgres'),
                'password': os.getenv('DB_PASSWORD', '')
            }
            # Enable SSL for remote databases (Aptible requires SSL)
            if db_host and db_host not in ('localhost', '127.0.0.1', '::1'):
                db_config['sslmode'] = 'require'
        
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT emr_id 
            FROM patients 
            WHERE emr_id IS NOT NULL 
            ORDER BY emr_id 
            LIMIT 10
        """)
        
        emr_ids = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        
        return emr_ids
    except Exception as e:
        print(f"⚠️  Could not fetch EMR IDs from database: {e}")
        return []


def test_patient_endpoint(emr_id):
    """Test the patient endpoint with a given EMR ID."""
    print("\n" + "=" * 60)
    print(f"Testing patient endpoint with EMR ID: {emr_id}")
    print("=" * 60)
    
    try:
        response = requests.get(f"{API_BASE_URL}/patient/{emr_id}")
        
        if response.status_code == 200:
            print("✅ Patient found!")
            data = response.json()
            print(f"\nPatient Details:")
            print(f"  EMR ID: {data.get('emr_id')}")
            print(f"  Name: {data.get('first_name')} {data.get('last_name')}")
            print(f"  Location: {data.get('location_name')}")
            print(f"  Phone: {data.get('mobile_phone')}")
            print(f"  DOB: {data.get('date_of_birth')}")
            print(f"  Captured at: {data.get('captured_at')}")
            return True
        elif response.status_code == 404:
            print(f"❌ Patient with EMR ID '{emr_id}' not found")
            print(f"   Response: {response.json().get('detail')}")
            return False
        else:
            print(f"❌ Unexpected status code: {response.status_code}")
            print(f"   Response: {response.json()}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API. Is the server running?")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    """Main test function."""
    print("\n🚀 FastAPI Patient Endpoint Tester\n")
    
    # Test root endpoint
    if not test_root_endpoint():
        print("\n❌ Root endpoint test failed. Please start the API server first.")
        print("   Run: python api.py")
        sys.exit(1)
    
    # Get EMR IDs from database
    print("\n" + "=" * 60)
    print("Fetching available EMR IDs from database...")
    print("=" * 60)
    emr_ids = get_emr_ids_from_db()
    
    if not emr_ids:
        print("⚠️  No EMR IDs found in database.")
        print("   You can test with a custom EMR ID by running:")
        print("   python test_api.py <emr_id>")
        
        # Try with a test EMR ID if provided as argument
        if len(sys.argv) > 1:
            test_emr_id = sys.argv[1]
            test_patient_endpoint(test_emr_id)
        else:
            print("\n   Or add some patient data to the database first.")
        return
    
    print(f"✅ Found {len(emr_ids)} EMR ID(s) in database")
    print(f"   EMR IDs: {', '.join(str(eid) for eid in emr_ids[:5])}")
    if len(emr_ids) > 5:
        print(f"   ... and {len(emr_ids) - 5} more")
    
    # Test with first EMR ID
    if emr_ids:
        test_patient_endpoint(emr_ids[0])
    
    # Test with custom EMR ID if provided
    if len(sys.argv) > 1:
        test_emr_id = sys.argv[1]
        if test_emr_id not in emr_ids:
            test_patient_endpoint(test_emr_id)
    
    print("\n" + "=" * 60)
    print("✅ Testing complete!")
    print("=" * 60)
    print("\n💡 Tips:")
    print("   - View interactive docs: http://localhost:8000/docs")
    print("   - Test with curl: curl http://localhost:8000/patient/<emr_id>")
    print("   - Test with custom EMR ID: python test_api.py <emr_id>")


if __name__ == "__main__":
    try:
        import requests
    except ImportError:
        print("❌ Error: 'requests' library not installed.")
        print("   Install it with: pip install requests")
        sys.exit(1)
    
    main()

