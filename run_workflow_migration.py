#!/usr/bin/env python3
"""
Run migration to rename uipath_status to workflow_status and verify changes.
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_success(msg):
    print(f"{GREEN}✓ {msg}{RESET}")

def print_error(msg):
    print(f"{RED}✗ {msg}{RESET}")

def print_info(msg):
    print(f"{YELLOW}ℹ {msg}{RESET}")

def print_step(msg):
    print(f"\n{BLUE}→ {msg}{RESET}")

def get_db_connection():
    """Get database connection using the same logic as the app."""
    database_url = os.getenv('DATABASE_URL')
    
    if database_url:
        try:
            from urllib.parse import urlparse
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
            if parsed.hostname and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
                db_config['sslmode'] = 'require'
            
            return psycopg2.connect(**db_config)
        except Exception as e:
            print_error(f"Error parsing DATABASE_URL: {e}")
            return None
    else:
        # Fall back to individual environment variables
        try:
            return psycopg2.connect(
                host=os.getenv('DB_HOST', 'localhost'),
                port=int(os.getenv('DB_PORT', '5432')),
                database=os.getenv('DB_NAME', 'solvhealth_patients'),
                user=os.getenv('DB_USER', 'postgres'),
                password=os.getenv('DB_PASSWORD', '')
            )
        except Exception as e:
            print_error(f"Database connection error: {e}")
            return None

def check_column_exists(conn, table_name, column_name):
    """Check if a column exists in a table."""
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = %s AND column_name = %s
        """, (table_name, column_name))
        return cursor.fetchone() is not None
    finally:
        cursor.close()

def check_index_exists(conn, index_name):
    """Check if an index exists."""
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE indexname = %s
        """, (index_name,))
        return cursor.fetchone() is not None
    finally:
        cursor.close()

def verify_migration(conn):
    """Verify that the migration was successful."""
    print_step("Verifying migration...")
    
    all_good = True
    
    # Check 1: workflow_status column exists
    if check_column_exists(conn, 'vm_health', 'workflow_status'):
        print_success("Column 'workflow_status' exists in vm_health table")
    else:
        print_error("Column 'workflow_status' NOT found in vm_health table")
        all_good = False
    
    # Check 2: uipath_status column does NOT exist
    if not check_column_exists(conn, 'vm_health', 'uipath_status'):
        print_success("Old column 'uipath_status' has been removed")
    else:
        print_error("Old column 'uipath_status' still exists!")
        all_good = False
    
    # Check 3: New index exists
    if check_index_exists(conn, 'idx_vm_health_workflow_status'):
        print_success("Index 'idx_vm_health_workflow_status' exists")
    else:
        print_error("Index 'idx_vm_health_workflow_status' NOT found")
        all_good = False
    
    # Check 4: Old index does NOT exist
    if not check_index_exists(conn, 'idx_vm_health_uipath_status'):
        print_success("Old index 'idx_vm_health_uipath_status' has been removed")
    else:
        print_error("Old index 'idx_vm_health_uipath_status' still exists!")
        all_good = False
    
    # Check 5: Alert sources updated
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM alerts WHERE source = 'uipath'")
        uipath_count = cursor.fetchone()[0]
        if uipath_count == 0:
            print_success(f"No alerts with source 'uipath' (all migrated to 'workflow')")
        else:
            print_error(f"Found {uipath_count} alerts still with source 'uipath'")
            all_good = False
        
        cursor.execute("SELECT COUNT(*) FROM alerts WHERE source = 'workflow'")
        workflow_count = cursor.fetchone()[0]
        print_info(f"Found {workflow_count} alerts with source 'workflow'")
    finally:
        cursor.close()
    
    # Check 6: Constraint updated
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT conname, pg_get_constraintdef(oid) as definition
            FROM pg_constraint 
            WHERE conrelid = 'alerts'::regclass 
            AND conname = 'alerts_source_check'
        """)
        result = cursor.fetchone()
        if result:
            definition = result[1]
            if "'workflow'" in definition and "'uipath'" not in definition:
                print_success("Alert source constraint updated correctly")
            else:
                print_error(f"Alert source constraint may not be updated: {definition}")
                all_good = False
        else:
            print_info("No alerts_source_check constraint found (may not exist yet)")
    finally:
        cursor.close()
    
    return all_good

def run_migration(conn):
    """Run the migration script."""
    print_step("Running migration...")
    
    cursor = conn.cursor()
    
    try:
        # Step 1: Check if column needs to be renamed
        if check_column_exists(conn, 'vm_health', 'uipath_status'):
            print_info("Renaming column uipath_status to workflow_status...")
            cursor.execute("ALTER TABLE vm_health RENAME COLUMN uipath_status TO workflow_status")
            print_success("Column renamed")
        elif check_column_exists(conn, 'vm_health', 'workflow_status'):
            print_info("Column already renamed (workflow_status exists)")
        else:
            print_error("Neither uipath_status nor workflow_status column found!")
            return False
        
        # Step 2: Update index
        if check_index_exists(conn, 'idx_vm_health_uipath_status'):
            print_info("Dropping old index...")
            cursor.execute("DROP INDEX IF EXISTS idx_vm_health_uipath_status")
            print_success("Old index dropped")
        
        if not check_index_exists(conn, 'idx_vm_health_workflow_status'):
            print_info("Creating new index...")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_vm_health_workflow_status ON vm_health(workflow_status)")
            print_success("New index created")
        else:
            print_info("New index already exists")
        
        # Step 3: Update alert sources
        cursor.execute("SELECT COUNT(*) FROM alerts WHERE source = 'uipath'")
        uipath_count = cursor.fetchone()[0]
        if uipath_count > 0:
            print_info(f"Updating {uipath_count} alerts from 'uipath' to 'workflow'...")
            cursor.execute("UPDATE alerts SET source = 'workflow' WHERE source = 'uipath'")
            print_success(f"Updated {cursor.rowcount} alerts")
        else:
            print_info("No alerts to update (already migrated)")
        
        # Step 4: Update constraint
        print_info("Updating alert source constraint...")
        cursor.execute("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_constraint 
                    WHERE conname = 'alerts_source_check' 
                    AND conrelid = 'alerts'::regclass
                ) THEN
                    ALTER TABLE alerts DROP CONSTRAINT alerts_source_check;
                END IF;
            END $$;
        """)
        cursor.execute("""
            ALTER TABLE alerts 
            ADD CONSTRAINT alerts_source_check 
            CHECK (source IN ('vm', 'server', 'workflow', 'monitor'))
        """)
        print_success("Constraint updated")
        
        conn.commit()
        return True
        
    except Exception as e:
        conn.rollback()
        print_error(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        cursor.close()

def test_api_fields(conn):
    """Test that the API can read/write with new field names."""
    print_step("Testing API field access...")
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Test 1: Insert a test VM health record with workflow_status
        test_vm_id = 'test-migration-vm-' + str(os.getpid())
        cursor.execute("""
            INSERT INTO vm_health (vm_id, status, workflow_status, last_heartbeat)
            VALUES (%s, 'healthy', 'running', CURRENT_TIMESTAMP)
            ON CONFLICT (vm_id) 
            DO UPDATE SET 
                workflow_status = EXCLUDED.workflow_status,
                last_heartbeat = CURRENT_TIMESTAMP
            RETURNING *
        """, (test_vm_id,))
        
        result = cursor.fetchone()
        if result and result.get('workflow_status') == 'running':
            print_success("Can write workflow_status field")
        else:
            print_error("Failed to write workflow_status field")
            return False
        
        # Test 2: Read the record back
        cursor.execute("""
            SELECT vm_id, workflow_status, status 
            FROM vm_health 
            WHERE vm_id = %s
        """, (test_vm_id,))
        
        result = cursor.fetchone()
        if result and 'workflow_status' in result:
            print_success("Can read workflow_status field")
        else:
            print_error("Failed to read workflow_status field")
            return False
        
        # Test 3: Query with workflow_status filter
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM vm_health 
            WHERE workflow_status = 'running'
        """)
        result = cursor.fetchone()
        if result:
            print_success(f"Can query by workflow_status (found {result['count']} records)")
        else:
            print_error("Failed to query by workflow_status")
            return False
        
        # Clean up test record
        cursor.execute("DELETE FROM vm_health WHERE vm_id = %s", (test_vm_id,))
        conn.commit()
        print_success("Test record cleaned up")
        
        return True
        
    except Exception as e:
        conn.rollback()
        print_error(f"API field test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        cursor.close()

def main():
    print(f"\n{BLUE}{'='*60}")
    print("Workflow Migration Script")
    print("="*60 + RESET)
    
    # Connect to database
    print_step("Connecting to database...")
    conn = get_db_connection()
    
    if not conn:
        print_error("Failed to connect to database")
        print_info("Make sure DATABASE_URL or DB_* environment variables are set")
        sys.exit(1)
    
    print_success("Connected to database")
    
    try:
        # Run migration
        if not run_migration(conn):
            print_error("Migration failed!")
            sys.exit(1)
        
        # Verify migration
        if not verify_migration(conn):
            print_error("Migration verification failed!")
            sys.exit(1)
        
        # Test API fields
        if not test_api_fields(conn):
            print_error("API field tests failed!")
            sys.exit(1)
        
        print(f"\n{GREEN}{'='*60}")
        print("✓ Migration completed successfully!")
        print("="*60 + RESET)
        print("\nAll checks passed:")
        print("  ✓ Database column renamed")
        print("  ✓ Indexes updated")
        print("  ✓ Alert sources migrated")
        print("  ✓ Constraints updated")
        print("  ✓ API can read/write new fields")
        
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()
        print_info("Database connection closed")

if __name__ == '__main__':
    main()
