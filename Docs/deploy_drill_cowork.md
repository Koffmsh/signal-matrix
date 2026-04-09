# Signal Matrix — Monthly Deploy Drill
# Cowork automation script
# Run: first weekday of each month, after 4:15 PM ET (market close)
# Purpose: keep the deploy path exercised; catch drift before it matters

---

## Context

- Project directory: C:\Users\shann\Projects\signal-matrix
- Fly.io apps: signal-matrix-api (512MB, iad) + signal-matrix-web (256MB, iad)
- Web deploy script: deploy-web.sh (must be run from project root — sources .env)
- Production API: https://api.signal.suttonmc.com
- Production web: https://signal.suttonmc.com

---

## Pre-conditions (check before starting)

- [ ] Docker Desktop is running
- [ ] VS Code / other apps have no uncommitted changes open
- [ ] It is after 4:15 PM ET on a weekday (avoid interrupting scheduler)
- [ ] Terminal is open in C:\Users\shann\Projects\signal-matrix

---

## Step 1 — Confirm clean working tree

```
git status
```

Expected: "nothing to commit, working tree clean"
If there are uncommitted changes: STOP. Do not proceed. Alert Shannon.

---

## Step 2 — Confirm Fly.io CLI auth

```
fly auth whoami
```

Expected: returns Shannon's Fly.io email address.
If auth is expired: run `fly auth login` and complete browser auth before continuing.

---

## Step 3 — Check API app status before deploy

```
fly status --app signal-matrix-api
```

Expected: "1 machines running" with state = "started"
If machine is stopped or unhealthy: STOP. Alert Shannon — do not deploy into a broken state.

---

## Step 4 — Check web app status before deploy

```
fly status --app signal-matrix-web
```

Expected: "1 machines running" with state = "started"
If unhealthy: STOP. Alert Shannon.

---

## Step 5 — Redeploy API app

```
fly deploy --app signal-matrix-api
```

Wait for deploy to complete. Expected output ends with:
"1 desired, 1 placed, 1 healthy, 0 unhealthy [health checks: 1 total, 1 passing]"

If deploy fails: STOP. Record the error output. Alert Shannon.

---

## Step 6 — Redeploy web app

```
./deploy-web.sh
```

This script sources .env and passes REACT_APP_ADMIN_PASSWORD as a build arg.
Do NOT run bare `fly deploy` for the web app — the admin password will not bake in.

Wait for deploy to complete. Same healthy output expected as Step 5.

If deploy fails: STOP. Record the error output. Alert Shannon.

---

## Step 7 — Confirm API responds post-deploy

```
curl https://api.signal.suttonmc.com/health
```

Expected: HTTP 200 with JSON response (e.g. `{"status": "ok"}`)
If this returns an error or timeout: STOP. Alert Shannon.

---

## Step 8 — Confirm web app loads post-deploy

Open in browser: https://signal.suttonmc.com

Expected: dashboard loads, tickers visible, no blank screen or error page.
If page fails to load: STOP. Alert Shannon.

---

## Step 9 — Confirm scheduler is live

```
curl https://api.signal.suttonmc.com/api/scheduler/status
```

Expected: JSON response with scheduler status. Key field: `"running": true`
If scheduler is not running: STOP. Alert Shannon — the API container may have lost state.

---

## Step 10 — Log the result

Append one line to Docs/deploy_drill_log.md in the project directory:

Format:
```
YYYY-MM-DD | PASS | All 9 steps completed. No issues.
```

Or if there were issues:
```
YYYY-MM-DD | PARTIAL | Failed at Step N: <brief description of error>
```

---

## Done

Drill complete. Total time: ~10–15 minutes.
If any step failed, Shannon should review before the next session with Neo.

---

## Failure Reference

| Symptom | Likely cause | Action |
|---|---|---|
| `fly auth whoami` fails | CLI auth expired | Run `fly auth login` |
| `fly deploy` fails with "no image" | Dockerfile changed, image stale | Run `fly deploy --rebuild` |
| `./deploy-web.sh` fails | .env missing REACT_APP_ADMIN_PASSWORD | Check .env, restart |
| `/health` returns 502 | Container crashed post-deploy | `fly logs --app signal-matrix-api` |
| Dashboard blank | API CORS issue or frontend built against wrong API URL | Check REACT_APP_API_URL in fly.web.toml |
| Scheduler not running | auto_stop_machines triggered despite config | Check fly.api.toml, redeploy |
