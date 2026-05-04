# Website QA Tester

An automated QA tool that audits websites for **UI issues** (overlapping elements, text cutoff, layout problems, misalignment) and verifies **Airtable integration** with the website's contact form. Accepts a single website URL or a CSV file containing multiple website domains for batch processing.

Built primarily for auditing German cleaning service landing pages, but the architecture is generalizable to any website.

---

## What It Does

The tool runs a **4-stage automated pipeline** on each website:

| Stage | What It Checks |
|-------|----------------|
| **1. Screenshot Capture** | Opens the website in a headless Chromium browser (1440x900 viewport), bypasses bot detection, and takes a full-page screenshot. |
| **2. Visual Analysis (AI)** | Sends the screenshot to Google Gemini 1.5 Flash to detect overlapping elements, text cutoff, layout breaks, and misalignment. Returns PASS or FAIL. *(Optional -- requires API key.)* |
| **3. Contact Form Test** | Navigates to the contact/Kontakt section, fills out all form fields with test data, and attempts submission. Detects success via URL redirect or on-page confirmation message. |
| **4. Airtable Verification** | Three-part check: **(B1)** Confirms the frontend JavaScript handler (`airtable-form-handler.js`) exists and is correctly configured for the domain. **(B2)** Bypasses the website form entirely and submits a test record directly to Airtable via REST API. **(C)** Polls Airtable to verify the record actually landed in the table. |

### Why the Airtable check uses the API directly

Website contact forms are often protected by CAPTCHA/Turnstile, which prevents automated clicking of the submit button. Instead of trying to solve the CAPTCHA, the tool reads the Airtable configuration from the website's JavaScript and then calls the Airtable API directly with the same credentials. This confirms the integration is wired up correctly end-to-end without needing to bypass anti-bot protections.

### Final Status

Each website receives a final verdict:

- **PASS** -- All enabled checks passed.
- **PARTIAL** -- Some checks passed, others failed or were skipped.
- **FAIL** -- Critical checks failed.

---

## Project Structure

```
.
├── visual_qa.py            # Main QA orchestrator (4-stage pipeline)
├── form_automation.py      # Contact form navigation and submission logic
├── airtable_verifier.py    # Airtable checks (B1/B2/C verification)
├── gemini_analyzer.py      # Google Gemini vision API wrapper
├── requirements.txt        # Python dependencies
├── webhook-server/         # Flask webhook server
│   ├── app.py              # Webhook endpoint for Airtable automation
│   ├── Dockerfile          # Docker container config
│   └── requirements.txt     # Flask dependencies
├── .env.example            # Environment variables template
├── data.csv                # Input: list of domains to test (CLI mode)
├── ui_report.csv           # Output: test results per domain
└── screenshots/            # Output: full-page screenshots per domain
```

---

## How to Start

### Option A: Webhook Server (Recommended for Production)

The webhook server listens for requests from Airtable and runs the QA pipeline automatically.

**Prerequisites:**
- Airtable automation configured (see COOLIFY_DEPLOYMENT.md)
- Coolify account with deployed application
- Environment variables set (AIRTABLE_LEADS_API_KEY, AIRTABLE_TRIGGER_API_KEY, etc.)

**How it works:**
1. Sales employee changes "Kontakt status" to "to be tested" in Airtable
2. Airtable automation sends webhook request to `/run-qa`
3. Webhook server runs the QA pipeline
4. Result (passed/failed) written back to "Kontakt status" field
5. Error details (if any) written to "Kontakt error" field

**For deployment instructions:** See [COOLIFY_DEPLOYMENT.md](COOLIFY_DEPLOYMENT.md)

### Option B: Command Line (Testing / Batch Mode)

For testing or batch processing:

```bash
python visual_qa.py
```

This reads domains from `data.csv` (must have a `domain` column) and writes results to `ui_report.csv`.

**Setup:**
```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
# Edit .env with your Airtable API keys and Gemini API key (optional)
python visual_qa.py
```

**Input:** `data.csv` with `domain` column  
**Output:** `ui_report.csv` + screenshots in `screenshots/` folder

---

## Input Format

### Webhook Server (Option A)
Input is received via HTTP POST:
```json
{
  "record_id": "recXXXXXXXXXXXXXX",
  "domain": "fensterreinigung-ulm.de"
}
```
Sent by Airtable automation when "Kontakt status" = "to be tested"

### Command Line (Option B)
Input is a CSV file with a `domain` column:

```csv
domain
fensterreinigungbruchsal.de
fensterreinigungstuttgart.de
fensterreinigungulm.de
```

**Note:** Domain should be bare (no `https://`); the tool adds it automatically.

---

## Output

### Report (`ui_report.csv`)

| Column | Description |
|--------|-------------|
| `domain` | Website tested |
| `status` | Final verdict: PASS, PARTIAL, or FAIL |
| `screenshot` | Path to the captured screenshot |
| `gemini_status` | PASS, FAIL, SKIPPED, or ERROR |
| `gemini_issues` | Pipe-separated list of detected visual issues |
| `form_status` | PASS or FAIL |
| `form_error` | Error details if form test failed |
| `airtable_linked` | Whether the frontend JS handler is correctly configured |
| `api_submission` | Whether a test record was successfully submitted to Airtable |
| `airtable_verified` | Whether the submitted record was found in Airtable |
| `error` | Any exception that occurred during testing |

### Screenshots (`screenshots/`)

Full-page PNG screenshots of each tested website, named by domain.

---

## Setup Requirements

### For Webhook Server Deployment (Production)

See [COOLIFY_DEPLOYMENT.md](COOLIFY_DEPLOYMENT.md) for complete setup instructions.

**Quick summary:**
- Git repository with code
- Coolify account (or VPS)
- 2 Airtable Personal Access Tokens
- Optional: Google Gemini API key

### For Local Testing (Command Line Mode)

**Prerequisites:**
- **Python 3.8+** — [Download from python.org](https://www.python.org/downloads/)
- **pip** — Comes bundled with Python
- **Git** — For version control (optional)

**Installation:**

```bash
# 1. Clone repository and install dependencies
git clone <your-repo-url>
cd test-cluade-api
pip install -r requirements.txt

# 2. Install Playwright browser engine (one-time)
playwright install chromium

# 3. Set up environment variables
cp .env.example .env
# Edit .env with your API keys
```

**Dependencies in `requirements.txt`:**

| Package | Purpose |
|---------|---------|
| `pandas` | CSV reading and writing |
| `playwright` | Headless browser automation |
| `requests` | HTTP requests (Airtable API) |
| `playwright-stealth` | Anti-bot detection bypass |
| `google-generativeai` | Google Gemini vision API |
| `Pillow` | Image processing |
| `python-dotenv` | Environment variable loading |
| `Flask` | Webhook server (if running locally) |
| `gunicorn` | Production WSGI server |

**Environment Variables:**

Copy `.env.example` to `.env` and fill in:

```bash
# Required for test lead submissions
AIRTABLE_LEADS_API_KEY=pat...
AIRTABLE_LEADS_BASE_ID=appL4PpAWoTl3rEzE
AIRTABLE_LEADS_TABLE=Leads Partner

# Required for trigger + result write-back
AIRTABLE_TRIGGER_API_KEY=pat...
AIRTABLE_TRIGGER_BASE_ID=apphwncsSpj5PTIFX
AIRTABLE_TRIGGER_TABLE=EMD Webseiten
AIRTABLE_TRIGGER_DOMAIN_FIELD=Domain
AIRTABLE_TRIGGER_RESULT_FIELD=Kontakt status
AIRTABLE_TRIGGER_ERROR_FIELD=Kontakt error

# Optional: Visual analysis with AI
GEMINI_API_KEY=your_key_here
```

Get API keys from:
- **Airtable:** airtable.com → Account Settings → Developer Hub
- **Gemini:** aistudio.google.com/apikey

### For End Users (Sales Team)

**You need:**
- Airtable account with edit access to "EMD Webseiten" table
- Modern web browser
- Nothing else!

Webhook server will be running in the cloud. Just change "Kontakt status" field to "to be tested" and wait for results.

---

## Configuration

All sensitive configuration (API keys, base IDs) is managed via environment variables. No hardcoding of secrets!

### Environment Variables

Set these in `.env` file or in your deployment platform (Coolify, Docker, etc.):

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `AIRTABLE_LEADS_API_KEY` | Yes | — | API key for test lead submissions |
| `AIRTABLE_LEADS_BASE_ID` | No | `appL4PpAWoTl3rEzE` | Base ID for test leads |
| `AIRTABLE_LEADS_TABLE` | No | `Leads Partner` | Table name for test leads |
| `AIRTABLE_TRIGGER_API_KEY` | Yes | — | API key for result write-back |
| `AIRTABLE_TRIGGER_BASE_ID` | No | `apphwncsSpj5PTIFX` | Base ID for trigger table |
| `AIRTABLE_TRIGGER_TABLE` | No | `EMD Webseiten` | Table name for trigger |
| `AIRTABLE_TRIGGER_DOMAIN_FIELD` | No | `Domain` | Field containing website URL |
| `AIRTABLE_TRIGGER_RESULT_FIELD` | No | `Kontakt status` | Field for PASS/FAIL result |
| `AIRTABLE_TRIGGER_ERROR_FIELD` | No | `Kontakt error` | Field for error messages |
| `GEMINI_API_KEY` | No | — | Google Gemini API key (optional) |

### Hardcoded Settings

These are safe to modify in source code if needed:

| Setting | Location | Default |
|---------|----------|---------|
| Browser viewport | `visual_qa.py` line ~82 | 1440 x 900 |
| Navigation timeout | `visual_qa.py` line ~82 | 30 seconds |
| Airtable retry attempts | `visual_qa.py` line ~116 | 3 retries |
| Airtable retry delay | `visual_qa.py` line ~117 | 4 seconds |
| Test form data | `form_automation.py` line ~28 | Name: "QA Test", Email: qa+{run_id}@test.com |

### For Webhook Server

When deploying to Coolify or Docker, set environment variables in:
- **Coolify:** Settings → Environment Variables
- **Docker:** Use `-e` flag or environment file
- **Local:** Edit `.env` file

---

## How It Works Under the Hood

### Form Navigation Strategy

The form automation module uses a three-strategy fallback to find the contact form:

1. **Click navigation link** -- Looks for nav links matching "kontakt", "contact", or "anfrage"
2. **Try direct URLs** -- Navigates to `/kontakt`, `/contact`, etc.
3. **Scroll to anchor** -- Looks for `#kontakt`, `#contact` anchors on the page

### Airtable Verification Flow

```
B1: Check frontend JS handler exists
    └── Fetch /js/airtable-form-handler.js
    └── Verify collectFormData function present
    └── Verify domain matches

B2: Submit test record via API
    └── POST to Airtable REST API
    └── Uses unique email: qa+{run_id}@test.com

C:  Verify record landed
    └── Query Airtable with FIND() formula
    └── Retry 3 times with 4-second delays
```

### Bot Detection Bypass

The tool uses `playwright-stealth` to avoid being blocked by anti-bot systems. It spoofs the Chrome runtime, hides the WebDriver flag, patches the Permissions API, and sets consistent User-Agent headers. Each domain gets an isolated browser context with separate cookies and cache.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Python is not installed" error | Install Python 3.8+ from python.org. Check "Add to PATH" during install. |
| Playwright browser not found | Run `playwright install chromium` in Command Prompt. |
| GUI doesn't open | Run `python gui.py` from Command Prompt to see error details. |
| Website times out | The default timeout is 30 seconds. Slow websites may need a higher timeout (edit `NAVIGATION_TIMEOUT` in `visual_qa.py`). |
| Airtable check fails | Verify the API key and base ID in `visual_qa.py` are correct and the table exists. |
| Gemini analysis shows "SKIPPED" | This is normal if `GEMINI_API_KEY` environment variable is not set. The tool works without it. |
| Form test fails with "Submit button not found" | The website's form structure may not match expected selectors. Check form field names in `form_automation.py`. |
