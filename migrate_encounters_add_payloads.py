#!/usr/bin/env python3
"""
Migration script to add raw_payload and parsed_payload columns to encounters table.
Run this to update your existing database schema.
"""

import os
import sys
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

def get_db_connection():
    """Get database connection"""
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
        except Exception as e:
            print(f"❌ Error parsing DATABASE_URL: {e}")
            return None
    else:
        db_host = os.getenv('DB_HOST', 'localhost')
        db_config = {
            'host': db_host,
            'port': os.getenv('DB_PORT', '5432'),
            'database': os.getenv('DB_NAME', 'solvhealth_patients'),
            'user': os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', ''),
        }
        if db_host and db_host not in ('localhost', '127.0.0.1', '::1'):
            db_config['sslmode'] = 'require'
    
    try:
        conn = psycopg2.connect(**db_config)
        return conn
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return None

def migrate_encounters_table():
    """Add raw_payload and parsed_payload columns to encounters table"""
    print("=" * 80)
    print("MIGRATION: Add raw_payload and parsed_payload to encounters table")
    print("=" * 80)
    print()
    
    conn = get_db_connection()
    if not conn:
        print("❌ Could not connect to database")
        print("\n💡 Make sure your database is running and .env file is configured")
        return False
    
    try:
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'encounters'
            )
        """)
        table_exists = cursor.fetchone()[0]
        
        if not table_exists:
            print("⚠️  'encounters' table does not exist")
            print("   Run app/database/schema.sql first to create the table")
            cursor.close()
            conn.close()
            return False
        
        print("✅ 'encounters' table exists")
        
        # Check if columns already exist
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'encounters' 
            AND column_name IN ('raw_payload', 'parsed_payload')
        """)
        existing_columns = [row[0] for row in cursor.fetchall()]
        
        if 'raw_payload' in existing_columns and 'parsed_payload' in existing_columns:
            print("✅ Columns 'raw_payload' and 'parsed_payload' already exist")
            print("   No migration needed!")
            cursor.close()
            conn.close()
            return True
        
        # Add columns
        print("\n📝 Adding columns...")
        
        if 'raw_payload' not in existing_columns:
            print("   Adding 'raw_payload JSONB'...")
            cursor.execute("""
                ALTER TABLE encounters
                ADD COLUMN raw_payload JSONB;
            """)
            print("   ✅ Added 'raw_payload'")
        else:
            print("   ⏭️  'raw_payload' already exists")
        
        if 'parsed_payload' not in existing_columns:
            print("   Adding 'parsed_payload JSONB'...")
            cursor.execute("""
                ALTER TABLE encounters
                ADD COLUMN parsed_payload JSONB;
            """)
            print("   ✅ Added 'parsed_payload'")
        else:
            print("   ⏭️  'parsed_payload' already exists")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("\n✅ Migration completed successfully!")
        print("\n💡 The encounters table now has raw_payload and parsed_payload columns")
        return True
        
    except psycopg2.Error as e:
        print(f"\n❌ Database error: {e}")
        if conn:
            conn.rollback()
            cursor.close()
            conn.close()
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.close()
        return False

def main():
    """Main function"""
    success = migrate_encounters_table()
    
    if success:
        print("\n" + "=" * 80)
        print("✅ MIGRATION SUCCESSFUL")
        print("=" * 80)
        print("\n💡 You can now test the encounter endpoint:")
        print("   python3 test_encounter_feature.py")
        return 0
    else:
        print("\n" + "=" * 80)
        print("❌ MIGRATION FAILED")
        print("=" * 80)
        return 1

if __name__ == "__main__":
    sys.exit(main())

