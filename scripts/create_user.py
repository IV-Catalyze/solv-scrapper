#!/usr/bin/env python3
"""
Script to create users in the database from the backend.

Usage:
    python scripts/create_user.py --username admin --password secret123
    python scripts/create_user.py --username user1 --password pass123 --email user1@example.com
"""

import sys
import os
import argparse
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils.user_auth import create_user, get_user_by_username
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def main():
    parser = argparse.ArgumentParser(
        description="Create a new user in the database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/create_user.py --username admin --password secret123
  python scripts/create_user.py --username user1 --password pass123 --email user1@example.com
        """
    )
    
    parser.add_argument(
        "--username",
        required=True,
        help="Username for the new user"
    )
    
    parser.add_argument(
        "--password",
        required=True,
        help="Password for the new user"
    )
    
    parser.add_argument(
        "--email",
        default=None,
        help="Email address for the new user (optional)"
    )
    
    args = parser.parse_args()
    
    # Check if user already exists
    existing_user = get_user_by_username(args.username)
    if existing_user:
        print(f"❌ Error: User '{args.username}' already exists!")
        sys.exit(1)
    
    # Create user
    print(f"Creating user '{args.username}'...")
    user = create_user(
        username=args.username,
        password=args.password,
        email=args.email
    )
    
    if user:
        print(f"✅ User '{args.username}' created successfully!")
        print(f"   ID: {user['id']}")
        if user.get('email'):
            print(f"   Email: {user['email']}")
    else:
        print(f"❌ Error: Failed to create user '{args.username}'")
        print("   Check database connection and ensure users table exists.")
        sys.exit(1)


if __name__ == "__main__":
    main()

