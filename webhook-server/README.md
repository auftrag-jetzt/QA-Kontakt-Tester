# Webhook Server for Airtable QA Automation

This Flask server listens for HTTP requests from Airtable and automatically runs the QA pipeline on websites.

---

## How It Works

1. **Airtable clicks button** → sends POST request to this server
2. **Server receives** domain name + record ID
3. **Server calls** `run_domain()` from `visual_qa.py`
4. **QA pipeline runs** (screenshot → Gemini → form → Airtable checks)
5. **Result written back** to Airtable automatically

---

## Local Testing (Development)

### Prerequisites
- Python 3.8+
- Parent directory dependencies already installed (`requirements_gui.txt`)

### Install & Run

```bash
# From webhook-server folder
pip install -r requirements.txt

# Run the server
python app.py
```

Server will listen on `http://localhost:5000`

### Test with curl

```bash
curl -X POST http://localhost:5000/run-qa \
  -H "Content-Type: application/json" \
  -d '{
    "record_id": "rec123456",
    "domain": "fensterreinigung-ulm.de"
  }'
```

Expected response:
```json
{
  "status": "PASS",
  "message": "QA run completed",
  "details": {
    "domain": "fensterreinigung-ulm.de",
    "gemini_status": "PASS",
    "form_status": "PASS",
    "airtable_verified": true
  }
}
```

### Available Endpoints

- `POST /run-qa` — Run QA pipeline
- `GET /health` — Health check
- `GET /` — API documentation

---

## Deploy to Coolify

### Option 1: Docker (Recommended)

1. **Push to Git** (if using Coolify's Git integration)
   ```bash
   git add webhook-server/
   git commit -m "Add webhook server"
   git push
   ```

2. **In Coolify:**
   - Go to "Projects" → Create new project
   - Add service → Docker
   - Point to `Dockerfile` in `webhook-server/`
   - Set environment: `PORT=5000`
   - Deploy

3. **Get your public URL** (e.g., `https://your-domain.com`)

### Option 2: Manual (Without Docker)

1. **SSH into your Coolify server**
   ```bash
   ssh user@your-server.com
   cd /home/apps/
   ```

2. **Clone/copy the code**
   ```bash
   git clone <your-repo>
   cd test-cluade-api
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements_gui.txt
   cd webhook-server
   pip install -r requirements.txt
   cd ..
   ```

4. **Install Playwright**
   ```bash
   playwright install chromium
   ```

5. **Run with gunicorn** (production-safe)
   ```bash
   gunicorn --bind 0.0.0.0:5000 --workers 1 --timeout 300 webhook-server.app:app
   ```

6. **Setup nginx** (reverse proxy with SSL)
   ```nginx
   server {
       listen 443 ssl;
       server_name your-domain.com;

       location / {
           proxy_pass http://127.0.0.1:5000;
           proxy_set_header Host $host;
       }
   }
   ```

---

## Configure Airtable Automation

Once your webhook has a public URL:

1. **In Airtable:** Open "EMD Webseiten" base
2. **Add automation:**
   - Trigger: "When a button is clicked"
   - Action: "Send a webhook"
   - URL: `https://your-domain.com/run-qa`
   - Method: POST
   - Headers: `Content-Type: application/json`
   - Body:
     ```json
     {
       "record_id": {record_id},
       "domain": {Domain}
     }
     ```

3. **Test:**
   - Click the button on a test record
   - Check Coolify logs for request
   - Verify "Kontakt status" field updates with PASS/PARTIAL/FAIL

---

## Environment Variables

The Airtable API tokens are **required** and read from the environment — they are no longer hardcoded in `visual_qa.py`. See [`.env.example`](../.env.example) in the parent folder for the full list with comments.

### Required

| Variable | Purpose |
|---|---|
| `AIRTABLE_LEADS_API_KEY` | Personal access token for the "Leads Partner" base — used by stages B2 + C (test-lead submission and verification). If unset, those stages are skipped. |
| `AIRTABLE_TRIGGER_API_KEY` | Personal access token for the "EMD Webseiten" base — used to write the PASS/FAIL verdict back to the triggering record. If unset, write-back is skipped. |

### Optional (have sensible defaults)

| Variable | Default |
|---|---|
| `AIRTABLE_LEADS_BASE_ID` | `appL4PpAWoTl3rEzE` |
| `AIRTABLE_LEADS_TABLE` | `Leads Partner` |
| `AIRTABLE_TRIGGER_BASE_ID` | `apphwncsSpj5PTIFX` |
| `AIRTABLE_TRIGGER_TABLE` | `EMD Webseiten` |
| `AIRTABLE_TRIGGER_DOMAIN_FIELD` | `Domain` |
| `AIRTABLE_TRIGGER_RESULT_FIELD` | `Kontakt status` |
| `GEMINI_API_KEY` | *(unset — stage 2 visual analysis is skipped if missing)* |

### Setting them

**Local development (bash/zsh):**
```bash
export AIRTABLE_LEADS_API_KEY=patXXXX...
export AIRTABLE_TRIGGER_API_KEY=patXXXX...
python app.py
```

**Coolify / Docker:** set them in the service's "Environment Variables" panel, or pass with `docker run -e AIRTABLE_LEADS_API_KEY=... -e AIRTABLE_TRIGGER_API_KEY=...`.

**Other useful runtime flags:**
```
FLASK_ENV=production
PYTHONUNBUFFERED=1
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| 500 error in webhook | Check server logs for `run_domain()` errors |
| Timeout on long tests | Increase gunicorn `--timeout` (default 300s = 5 min) |
| "Module not found" | Ensure parent directory files are accessible (check `sys.path` in `app.py`) |
| Webhook not received | Verify Airtable automation is configured correctly + public URL is accessible |

---

## Notes

- Server runs **one test at a time** (workers=1). If you need parallel runs, increase `--workers` but ensure your system can handle multiple browser instances.
- Each test takes **2-5 minutes** (depends on website speed + Gemini API).
- Results are written back to Airtable automatically via `write_qa_result_to_airtable()`.
- Check Coolify logs to monitor requests and debug issues.
