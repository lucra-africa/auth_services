"""CLI for admin operations (run outside of the web server)."""

import argparse
import asyncio
import getpass
import sys
from datetime import datetime, timezone

from src.config import settings
from src.core.security import hash_password, validate_password_strength
from src.db.mongo import init_database, close_database, get_db
from src.models.enums import UserRole


async def create_admin(email: str, password: str) -> None:
    await init_database()
    db = get_db()

    existing = await db.users.find_one({"email": email.lower().strip()})
    if existing:
        print(f"Error: User with email '{email}' already exists.")
        await close_database()
        sys.exit(1)

    violations = validate_password_strength(password)
    if violations:
        print("Password does not meet requirements:")
        for v in violations:
            print(f"  - {v}")
        await close_database()
        sys.exit(1)

    now = datetime.now(timezone.utc)
    user_doc = {
        "email": email.lower().strip(),
        "password_hash": hash_password(password),
        "role": UserRole.ADMIN.value,
        "is_email_verified": True,
        "is_active": True,
        "profile_completed": True,
        "profile": {
            "first_name": "System",
            "last_name": "Administrator",
            "phone": None,
            "company_name": None,
            "avatar_url": None,
            "metadata": {},
        },
        "failed_login_attempts": 0,
        "locked_until": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.users.insert_one(user_doc)
    print(f"Admin user created: {email}")

    await close_database()


def main():
    parser = argparse.ArgumentParser(description="Poruta Auth Service CLI")
    subparsers = parser.add_subparsers(dest="command")

    create_parser = subparsers.add_parser("create-admin", help="Create an admin user")
    create_parser.add_argument("--email", required=True, help="Admin email address")
    create_parser.add_argument("--password", help="Admin password (will prompt if not provided)")

    args = parser.parse_args()

    if args.command == "create-admin":
        password = args.password
        if not password:
            password = getpass.getpass("Enter admin password: ")
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                print("Error: Passwords do not match.")
                sys.exit(1)

        asyncio.run(create_admin(args.email, password))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
