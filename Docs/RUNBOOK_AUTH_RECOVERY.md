# Auth Recovery Runbook

## When to use

You cannot log in to https://signal.suttonmc.com — wrong password, disabled account, demoted account, or auth system bug.

---

## Recovery Path 1 — Direct Supabase reset (fastest, ~5 min)

1. Open Supabase dashboard → project **signal-matrix** → Table Editor → `users` table.
2. Find your row.
   - If `status` is `disabled` or `pending`, set it to `active`. Save.
   - If `role` is `viewer`, set it to `admin`. Save.
3. If the password is the issue, generate a new bcrypt hash on your machine in any Python shell:
   ```bash
   python -c "import bcrypt; print(bcrypt.hashpw(b'YourNewPassword123', bcrypt.gensalt()).decode())"
   ```
   (You can also run this inside Docker locally: `docker exec signal-matrix-backend-1 python -c "..."`.)
4. Paste the output into the `hashed_password` cell. Save.
5. Log in with the new password.

**Validated** — confirmed working 2026-05-08 during initial deploy by toggling `status = "disabled"` → login blocked → `status = "active"` → login restored.

---

## Recovery Path 2 — Recovery script via Fly.io SSH (~10 min)

```powershell
fly ssh console --app signal-matrix-api -C "python -m scripts.reset_admin"
```

The script reads `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_DISPLAY_NAME` from Fly.io secrets and either creates the admin (if no user with that email exists) or resets that user's password + sets role=admin + status=active. Idempotent — safe to re-run.

If `ADMIN_PASSWORD` on Fly.io is also lost, set a new one first:

```powershell
fly secrets set ADMIN_PASSWORD="<new password — 24 char alphanumeric>" --app signal-matrix-api
# then re-run the recovery script
fly ssh console --app signal-matrix-api -C "python -m scripts.reset_admin"
```

Note: setting Fly.io secrets restarts the API. Run the recovery script after the new machine is healthy.

---

## Recovery Path 3 — Re-seed from scratch (~15 min, last resort)

Nukes the entire `users` table. Use only if Paths 1 and 2 fail and you're willing to recreate every user.

```powershell
fly ssh console --app signal-matrix-api -C "python -c \"from database import SessionLocal; from models.user import User; db=SessionLocal(); db.query(User).delete(); db.commit(); print('All users deleted')\""
fly machine restart --app signal-matrix-api
```

On restart, `seed_admin_if_empty` recreates the admin from env vars. **WARNING:** every other user (including viewers you've activated) is also deleted.

---

## Recovery Path 4 — JWT_SECRET lost or rotated

If the production `JWT_SECRET` is lost (replaced with a new value), every existing session cookie becomes invalid. The cookie data is unchanged, but signature verification fails — every user is forced to re-login. Their accounts and passwords are unaffected.

To rotate intentionally:

```powershell
# Generate new secret in your own PowerShell — don't paste into chat
docker exec signal-matrix-backend-1 python -c "import secrets; print(secrets.token_urlsafe(32))"
# Save to Google Password Manager
# Set on Fly.io
fly secrets set JWT_SECRET="<new value>" --app signal-matrix-api
```

API restarts; all sessions invalidated; users re-login; new cookies signed with new secret.

---

## Routine: activate a pending user

1. Log in at https://signal.suttonmc.com as admin.
2. Profile menu (top-right) → **ADMIN PANEL** → **USERS** tab.
3. Click **ACTIVATE** on the pending row. Status flips to Active.
4. Tell the user out of band that they can now log in.

---

## Routine: admin-side password reset

Use when a user is locked out and the email-based forgot-password flow isn't working (e.g., wrong email on file, mail server issue).

1. Log in as admin → **ADMIN PANEL** → **USERS** tab.
2. Click **RESET PW** on the user's row.
3. Enter a new password (12+ chars).
4. Communicate the new password to the user out of band — they should change it after logging in.

Backend endpoint used: `POST /api/users/{user_id}/reset-password`.
