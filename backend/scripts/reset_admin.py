"""
Recovery script — re-seed the admin account from env vars regardless of current state.

Run via: fly ssh console --app signal-matrix-api → python /app/scripts/reset_admin.py

Reads ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_DISPLAY_NAME from environment.
- If admin email exists: resets password, sets role=admin, status=active
- If admin email does not exist: creates the user fresh
- Idempotent — safe to run repeatedly
"""

import os
import sys

sys.path.insert(0, "/app")

from database import SessionLocal
from models.user import User
from services.auth_service import hash_password


def reset_admin():
    email = os.getenv("ADMIN_EMAIL")
    password = os.getenv("ADMIN_PASSWORD")
    name = os.getenv("ADMIN_DISPLAY_NAME", "Admin")

    if not email or not password:
        print("ERROR: ADMIN_EMAIL and ADMIN_PASSWORD must be set.")
        sys.exit(1)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.hashed_password = hash_password(password)
            user.role = "admin"
            user.status = "active"
            user.display_name = name
            db.commit()
            print(f"Admin reset: {email} (existing record updated)")
        else:
            user = User(
                email=email,
                display_name=name,
                hashed_password=hash_password(password),
                role="admin",
                status="active",
            )
            db.add(user)
            db.commit()
            print(f"Admin created: {email} (new record)")
    finally:
        db.close()


if __name__ == "__main__":
    reset_admin()
