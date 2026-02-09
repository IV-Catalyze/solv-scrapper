#!/usr/bin/env python3
"""
User authentication utilities for session-based authentication.

Provides password hashing, verification, and user database operations.
"""

import os
from typing import Optional, Dict, Any
from passlib.context import CryptContext
from passlib.hash import bcrypt
import psycopg2
from psycopg2.extras import RealDictCursor

# Password hashing context
# Use bcrypt directly to avoid version compatibility issues
try:
    import bcrypt
    USE_DIRECT_BCRYPT = True
except ImportError:
    USE_DIRECT_BCRYPT = False
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    if USE_DIRECT_BCRYPT:
        # Use bcrypt directly
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    else:
        return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    if USE_DIRECT_BCRYPT:
        # Use bcrypt directly
        try:
            return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
        except Exception:
            return False
    else:
        return pwd_context.verify(plain_password, hashed_password)


def get_db_connection():
    """Get database connection using environment variables."""
    # Support DATABASE_URL for cloud deployments (Aptible, etc.)
    database_url = os.getenv('DATABASE_URL')
    
    if database_url:
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
                'password': parsed.password or '',
            }
            # Enable SSL for remote databases
            if parsed.hostname and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
                db_config['sslmode'] = 'require'
            
            return psycopg2.connect(**db_config)
        except Exception as e:
            # Fall back to individual env vars if DATABASE_URL parsing fails
            pass
    
    # Fall back to individual environment variables
    try:
        return psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', '5432')),
            database=os.getenv('DB_NAME', 'solvhealth_patients'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', ''),
        )
    except psycopg2.Error as e:
        # Don't print in production - use logging instead
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Database connection error: {e}")
        return None


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Get user by username from database."""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            "SELECT id, username, email, password_hash, is_active FROM users WHERE username = %s",
            (username,)
        )
        result = cursor.fetchone()
        cursor.close()
        return dict(result) if result else None
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching user: {e}")
        return None
    finally:
        conn.close()


def get_user_by_username_or_email(identifier: str) -> Optional[Dict[str, Any]]:
    """Get user by username or email from database."""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            "SELECT id, username, email, password_hash, is_active FROM users WHERE username = %s OR email = %s",
            (identifier, identifier)
        )
        result = cursor.fetchone()
        cursor.close()
        return dict(result) if result else None
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching user: {e}")
        return None
    finally:
        conn.close()


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Authenticate a user by username/email and password.
    Supports both username and email as the identifier.
    
    Returns user dict without password_hash if authentication succeeds, None otherwise.
    """
    # Try to get user by username or email
    user = get_user_by_username_or_email(username)
    if not user:
        return None
    
    if not user.get('is_active', True):
        return None
    
    if not verify_password(password, user['password_hash']):
        return None
    
    # Return user without password_hash
    user_dict = {
        'id': user['id'],
        'username': user['username'],
        'email': user.get('email'),
        'is_active': user.get('is_active', True),
    }
    return user_dict


def create_user(username: str, password: str, email: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Create a new user in the database.
    
    Returns user dict if successful, None otherwise.
    """
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        password_hash = get_password_hash(password)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            """
            INSERT INTO users (username, email, password_hash, is_active)
            VALUES (%s, %s, %s, %s)
            RETURNING id, username, email, is_active
            """,
            (username, email, password_hash, True)
        )
        
        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        
        return dict(result) if result else None
    except psycopg2.IntegrityError as e:
        conn.rollback()
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"User creation error (duplicate username/email): {e}")
        return None
    except Exception as e:
        conn.rollback()
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error creating user: {e}")
        return None
    finally:
        conn.close()

