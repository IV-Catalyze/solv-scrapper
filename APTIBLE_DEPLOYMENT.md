# Aptible Deployment Guide

Use this document as the canonical runbook for building, configuring, and deploying the patient-form capture stack on Aptible.

## 1. Prerequisites

- Aptible CLI installed locally (`brew install aptible` or see Aptible docs).
- Access to an Aptible environment with permission to create apps and databases.
- Git access to this repository and the ability to push to the branch you will deploy from.
- SolvHealth management portal credentials to test end-to-end once deployed.

## 2. Build & Test Locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Set required env vars for local smoke test
export SOLVHEALTH_QUEUE_URL="https://manage.solvhealth.com/queue?location_ids=AXjwbE"
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=solvhealth_patients
export DB_USER=postgres
export DB_PASSWORD=...

# Optional: force headless mode locally via environment flag
export PLAYWRIGHT_HEADLESS=1

# Run API and monitor individually or via run_all.py
python api.py
python monitor_patient_form.py
```

For a containerized smoke test:

```bash
docker build -t patient-form:local .
docker run -it --rm \
  -e SOLVHEALTH_QUEUE_URL=... \
  -e DB_HOST=... -e DB_PORT=... \
  -e DB_NAME=... -e DB_USER=... -e DB_PASSWORD=... \
  -p 8000:8000 patient-form:local uvicorn api:app --host 0.0.0.0 --port 8000
```

## 3. Provision Aptible Resources

```bash
aptible login
aptible apps:create patient-form-prod
aptible db:create patient-form-db --type postgresql --version 15
aptible db:credentials:rotate patient-form-db
```

Record the database URL or individual credentials from the rotate command.

## 4. Configure Environment Variables

```bash
aptible config:set --app patient-form-prod \
  SOLVHEALTH_QUEUE_URL="https://manage.solvhealth.com/queue?location_ids=AXjwbE" \
  DB_HOST=<db host> \
  DB_PORT=<db port> \
  DB_NAME=<db name> \
  DB_USER=<db user> \
  DB_PASSWORD=<db password> \
  PLAYWRIGHT_HEADLESS=1
```

Optional overrides:

- `API_PORT` – set only if you need the API to listen on a specific internal port. Aptible sets `PORT` automatically.
- `RUN_ALL_AUTOSTART_DB=0` – prevents `run_all.py` from attempting to manage the database (default already aligns with container deployments).

## 5. Deploy

Ensure your branch contains the `Dockerfile`, `Procfile`, and `aptible.yml`.

```bash
git push origin <branch>
aptible deploy --app patient-form-prod
```

The Aptible CLI builds the Docker image, uploads it, and creates two service instances (`web`, `worker`) as defined in `aptible.yml`.

## 6. Post-Deploy Verification

1. Tail logs:
   ```bash
   aptible logs --app patient-form-prod --process web
   aptible logs --app patient-form-prod --process worker
   ```
2. Hit the API root: `curl https://patient-form-prod.<env>.aptible.in/` (replace with actual hostname).
3. Validate `/patients` response for expected data.
4. Trigger a form submission in SolvHealth to confirm the worker captures and persists data.

## 7. Maintenance Tasks

- **Database backups**: Aptible manages snapshots automatically; review retention policies per environment.
- **Credential rotation**: use `aptible config:set` to rotate DB credentials and redeploy.
- **Scaling**: Adjust `aptible.yml` counts (e.g., scale `worker` to 2), then redeploy.
- **Monitoring**: Subscribe to Aptible metrics and alerts for `web` and `worker` to detect failures quickly.

## 8. Troubleshooting

- **Worker exits immediately**: Check `PLAYWRIGHT_HEADLESS`; Playwright cannot launch a non-headless browser without a display in Aptible.
- **Database connection errors**: Confirm firewall rules and credential accuracy; rerun `aptible db:tunnel` for manual inspection.
- **API returns 502**: Tail `web` logs; ensure the service is listening on `0.0.0.0` and the provided `$PORT`.

For deeper issues, open a ticket with Aptible support and include relevant log excerpts.


