# AI Context — Website QA Automation System

> This file is for AI assistants. Share it alongside Airtable screenshots to get
> precise answers about table structure, fields, automation triggers, etc.
> Skip to the section most relevant to your question.

---

## What This System Does (One Paragraph)

A Python script (`visual_qa.py`) takes a website domain, opens it in a headless
Chromium browser, and runs four sequential checks:
1. Takes a full-page screenshot
2. Sends the screenshot to Google Gemini for visual defect detection
3. Navigates to the contact form, fills it with test data, and submits it
4. Confirms the form's Airtable integration by directly submitting a test record
   via the Airtable REST API and then verifying the record was stored

The final verdict is **PASS**, **PARTIAL**, or **FAIL**.

**The goal being added now:** A sales employee clicks a button in Airtable
(no Python, no terminal). Airtable triggers this script automatically with the
domain, the script runs end-to-end, and writes the result back to the same
Airtable record. Zero tech involvement from the user.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Browser automation | Playwright (async, Python) + playwright-stealth |
| Visual analysis | Google Gemini 1.5 Flash (vision API) |
| HTTP / API calls | Python `requests` library |
| Airtable integration | Airtable REST API v0 |
| Runtime | Python 3.8+, runs on any machine with internet access |
| No GUI | No desktop UI — pure script, triggered externally |

---

## System Architecture

```
[Airtable — Trigger Table]
  └─ Sales employee clicks button on a record
       │
       │  Airtable Automation sends:
       │    POST { "record_id": "recXXX", "domain": "example.de" }
       ▼
[Webhook / Polling Script]          ← component TO BE BUILT
  └─ calls run_domain(domain, record_id)
       │
       ▼
[visual_qa.py — run_domain()]       ← already built
  ├─ Stage 1: Screenshot (Playwright)
  ├─ Stage 2: Gemini visual check
  ├─ Stage 3: Form submission test (Playwright)
  └─ Stage 4: Airtable integration test (REST API → Leads table)
       │
       │  Returns: { "status": "PASS"|"PARTIAL"|"FAIL", ... }
       │
       ▼
[write_qa_result_to_airtable()]     ← already built
  └─ PATCH /v0/{base_id}/{table}/{record_id}
       { "fields": { "<qa_result_field>": "PASS" } }
       │
       ▼
[Airtable — Trigger Table record updated]
  └─ Sales employee sees PASS / FAIL in the result field
```

---

## Two Separate Airtable Tables

This system interacts with **two different Airtable tables** that must not be
confused:

### Table A — Leads / Form Test Target (`AIRTABLE_LEADS_CONFIG`)
- **Purpose:** The pipeline submits a fake test lead here (stage 4) to verify the
  website's contact form is wired to Airtable correctly.
- **Direction:** Script → Airtable (write only during test, then read to verify)
- **Currently configured:** base `appL4PpAWoTl3rEzE`, table `Leads Partner`
- **Fields written by the script:**

  | Field | Value written |
  |---|---|
  | `Name` | `"QA Test"` |
  | `E-Mail` | `"qa+{run_id}@test.com"` (unique per run) |
  | `Website` | domain being tested, e.g. `"fensterreinigung-ulm.de"` |
  | `Telefon` | `"1234567890"` |
  | `Nachricht` | `"Automated QA Test"` |

### Table B — Trigger & Result Table (`AIRTABLE_TRIGGER_CONFIG`)
- **Purpose:** Sales employees manage website records here. One click triggers
  the QA run. The result is written back to the same record.
- **Direction:** Airtable → Script (trigger) then Script → Airtable (write-back)
- **Currently configured:** ALL PLACEHOLDERS — needs to be filled in.
- **Fields the script reads from this table:**

  | Placeholder key | What it should be | Example |
  |---|---|---|
  | `domain_field` | Field containing the website domain | `"Website"`, `"Domain"`, `"URL"` |

- **Fields the script writes to this table:**

  | Placeholder key | What it should be | Recommended type |
  |---|---|---|
  | `qa_result_field` | Field to receive PASS/FAIL | Single Select or Short Text |

---

## Public API — How Other Components Call This Script

### `run_domain(domain, airtable_record_id=None, run_id=None) → dict`

The single callable entry point. Synchronous (blocking). Safe to call from any
trigger script or webhook handler.

**Input:**
```python
domain              # str  — bare domain, e.g. "fensterreinigung-ulm.de"
                    #         "https://" is added automatically
airtable_record_id  # str  — Airtable record ID from the trigger table,
                    #         e.g. "recXXXXXXXXXXXXXX"
                    #         If provided → write-back happens automatically
run_id              # str  — optional, auto-generated if omitted
```

**Output dict:**
```python
{
    "domain":            "fensterreinigung-ulm.de",
    "status":            "PASS" | "PARTIAL" | "FAIL",
    "screenshot":        "screenshots/fensterreinigung-ulm.de.png",
    "gemini_status":     "PASS" | "FAIL" | "SKIPPED" | "ERROR",
    "gemini_issues":     "issue1 | issue2",   # pipe-separated string, or ""
    "form_status":       "PASS" | "FAIL",
    "form_error":        "",                  # error detail string if FAIL
    "airtable_linked":   True | False | None, # B1: JS handler present?
    "api_submission":    True | False | None, # B2: test record created?
    "airtable_verified": True | False | None, # C:  test record found?
    "error":             "",                  # top-level exception if any
}
```

**Status logic:**
- `PASS` — Gemini ok AND form ok AND API submission succeeded AND record verified
- `PARTIAL` — some checks passed, at least one failed or was inconclusive
- `FAIL` — critical failures (page unreachable, form broken, API rejected)

### `write_qa_result_to_airtable(record_id, status, cfg=None) → bool`

Standalone function. PATCHes one field on one record in Table B.

**Input:**
```python
record_id  # str — Airtable record ID, e.g. "recXXXXXXXXXXXXXX"
status     # str — "PASS", "PARTIAL", or "FAIL"
cfg        # dict — defaults to AIRTABLE_TRIGGER_CONFIG
```

**Airtable API call made:**
```
PATCH https://api.airtable.com/v0/{base_id}/{table_name}/{record_id}
Authorization: Bearer {api_key}
Content-Type: application/json

{ "fields": { "{qa_result_field}": "PASS" } }
```

---

## The Missing Component (what needs to be built next)

The glue between Airtable and `run_domain()` does not exist yet. Two options:

### Option A — Webhook Server (recommended)
A small HTTP server (Flask/FastAPI, ~30 lines) that:
- Listens on `POST /run-qa`
- Expects JSON body: `{ "record_id": "recXXX", "domain": "example.de" }`
- Calls `run_domain(domain, record_id)`
- Returns `{ "status": "PASS" }`

Airtable Automation: "When button clicked → Send webhook → POST /run-qa"

Hosting options: same machine (exposed via ngrok for testing), VPS, or any
server with Python + internet access.

### Option B — Polling Script (no server needed)
A scheduled script (Windows Task Scheduler or cron) that:
- Calls Airtable API to list records where `qa_result_field` is empty
- Calls `run_domain()` for each
- Write-back happens automatically inside `run_domain()`

---

## Configuration Reference (`visual_qa.py`)

```python
# Table A — test lead submissions
AIRTABLE_LEADS_CONFIG = {
    "api_key":    "pat...",          # Airtable personal access token
    "base_id":   "appL4PpAWoTl3rEzE",
    "table_name": "Leads Partner",
}

# Table B — trigger source + QA result write-back (NEEDS FILLING IN)
AIRTABLE_TRIGGER_CONFIG = {
    "api_key":         "PLACEHOLDER_API_KEY",
    "base_id":         "PLACEHOLDER_BASE_ID",
    "table_name":      "PLACEHOLDER_TABLE",
    "domain_field":    "PLACEHOLDER_DOMAIN_FIELD",   # read from this field
    "qa_result_field": "PLACEHOLDER_RESULT_FIELD",   # write result here
}
```

Other tunable constants:
```python
NAVIGATION_TIMEOUT = 30_000   # ms — per-page load timeout
WAIT_AFTER_LOAD    = 2_000    # ms — settle time after page load
_AT_RETRY_COUNT    = 3        # retries for Airtable record verification
_AT_RETRY_DELAY    = 4        # seconds between retries
```

---

## File Map

```
visual_qa.py          Main orchestrator. Contains run_domain(), write_qa_result_to_airtable(),
                      all 4 pipeline stages, AIRTABLE_LEADS_CONFIG, AIRTABLE_TRIGGER_CONFIG.

form_automation.py    Finds and fills the contact form on any website.
                      Input: Playwright page, domain str, run_id str
                      Output: { "status": "PASS"|"FAIL", "error": str }

gemini_analyzer.py    Sends a screenshot PNG to Gemini 1.5 Flash.
                      Input: filepath str
                      Output: { "status": "PASS"|"FAIL", "issues": [str, ...] }

airtable_verifier.py  Standalone B1/B2/C checks (not used directly — logic was
                      merged into visual_qa.py). Can be used as reference.

data.csv              Input for CLI batch mode. Column: "domain"
ui_report.csv         Output for CLI batch mode. One row per domain.
screenshots/          Full-page PNGs named by domain.
task.txt              Human checklist — what placeholder values still need filling.
AI_CONTEXT.md         This file.
```

---

## Questions This File Is Meant to Help Answer

When you share this file + Airtable screenshots with another AI, ask it to:

1. **Identify the trigger table** — which table/view the sales team uses, and
   what the record_id and domain field are named.
2. **Identify or create the result field** — what type (Single Select vs Text
   vs Checkbox) and what values to use for PASS / PARTIAL / FAIL.
3. **Design the Airtable Automation** — button trigger vs record-created trigger,
   what JSON payload to send to the webhook, and which URL to target.
4. **Confirm whether Table A and Table B share the same base/API key** — or
   whether a second personal access token is needed.
5. **Decide on Option A vs B** — webhook server or polling script, given the
   team's setup.
