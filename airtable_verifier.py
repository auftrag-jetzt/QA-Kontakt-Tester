"""
airtable_verifier.py — Airtable Linkage & Data Verification Module
===================================================================

Implements three QA layers that sit on top of the existing UI tests:

  B1 — Frontend JS validation  (verifies site is wired to Airtable)
  B2 — Direct Airtable API submission  (bypasses UI / CAPTCHA)
  C  — Airtable record verification    (confirms data was stored)

Configuration dict expected by every public function:
    {
        "api_key":    str,   # Airtable personal access token
        "base_id":   str,   # e.g. "appXXXXXXXXXXXXXX"
        "table_name": str,  # e.g. "Leads"
        "domain":    str,   # e.g. "example.de"
    }

Usage (from visual_qa.py):
    from airtable_verifier import run_airtable_checks

    airtable_result = await run_airtable_checks(page, config, test_email)
"""

import asyncio
import time
from urllib.parse import urlparse

import requests
from playwright.async_api import Page


# ─────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────

AIRTABLE_API_BASE = "https://api.airtable.com/v0"
JS_HANDLER_PATH   = "/js/airtable-form-handler.js"

RETRY_COUNT       = 3
RETRY_DELAY_S     = 4   # seconds between verification retries


# ─────────────────────────────────────────────────────────────
# Part B1 — Frontend JS Validation
# ─────────────────────────────────────────────────────────────

async def check_airtable_js_linkage(page: Page, base_url: str) -> dict:
    """
    Fetch /js/airtable-form-handler.js via Playwright and validate its content.

    Checks:
        1. File is reachable (HTTP 200)
        2. Contains the 'collectFormData' function
        3. Contains the 'Website' field reference
        4. Contains the current domain

    Returns:
        {
            "linked": bool,
            "details": str   — human-readable summary
        }
    """
    js_url = base_url.rstrip("/") + JS_HANDLER_PATH
    domain = urlparse(base_url).netloc

    try:
        response = await page.request.get(js_url)

        if response.status != 200:
            print(f"  [WARN] Airtable handler missing (HTTP {response.status}): {js_url}")
            return {"linked": False, "details": f"JS handler not found (HTTP {response.status})"}

        js_content = await response.text()

        # Keyword checks
        missing = []
        if "collectFormData" not in js_content:
            missing.append("'collectFormData' not found")
        if "Website" not in js_content:
            missing.append("'Website' field not found")
        if domain not in js_content:
            missing.append(f"domain '{domain}' not found in JS config")

        if missing:
            details = "; ".join(missing)
            print(f"  [ERROR] Airtable handler validation failed: {details}")
            return {"linked": False, "details": details}

        print(f"  [INFO] Airtable handler detected")
        print(f"  [INFO] Domain matches JS config")
        return {"linked": True, "details": "JS handler valid"}

    except Exception as exc:
        print(f"  [ERROR] Could not fetch Airtable JS handler: {exc}")
        return {"linked": False, "details": str(exc)}


# ─────────────────────────────────────────────────────────────
# Part B2 — Direct Airtable API Submission
# ─────────────────────────────────────────────────────────────

def _airtable_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }


def _table_url(config: dict) -> str:
    return f"{AIRTABLE_API_BASE}/{config['base_id']}/{config['table_name']}"


async def send_test_lead_to_airtable(config: dict, test_email: str) -> dict:
    """
    Send a test lead record directly to Airtable via the REST API.
    Uses requests (sync) wrapped in asyncio.to_thread for non-blocking execution.

    Returns:
        {
            "success": bool,
            "record_id": str | None,
            "details": str
        }
    """
    payload = {
        "records": [{
            "fields": {
                "Name":      "QA Test",
                "E-Mail":    test_email,
                "Website":   config["domain"],
                "Telefon":   "1234567890",
                "Nachricht": "Automated QA Test",
            }
        }]
    }

    def _post():
        return requests.post(
            _table_url(config),
            headers=_airtable_headers(config["api_key"]),
            json=payload,
            timeout=15,
        )

    try:
        response = await asyncio.to_thread(_post)

        if response.status_code in (200, 201):
            data      = response.json()
            record_id = data["records"][0]["id"]
            print(f"  [INFO] Airtable API submission successful (record: {record_id})")
            return {"success": True, "record_id": record_id, "details": "Record created"}

        print(f"  [ERROR] Airtable API failed (HTTP {response.status_code}): {response.text[:200]}")
        return {
            "success":   False,
            "record_id": None,
            "details":   f"HTTP {response.status_code}: {response.text[:200]}",
        }

    except Exception as exc:
        print(f"  [ERROR] Airtable API exception: {exc}")
        return {"success": False, "record_id": None, "details": str(exc)}


# ─────────────────────────────────────────────────────────────
# Part C — Airtable Record Verification
# ─────────────────────────────────────────────────────────────

async def verify_airtable_entry(config: dict, test_email: str) -> dict:
    """
    Poll Airtable up to RETRY_COUNT times to confirm the test record exists.

    Returns:
        {
            "verified": bool,
            "details":  str
        }
    """
    params = {"filterByFormula": f"{{E-Mail}} = '{test_email}'"}

    def _get():
        return requests.get(
            _table_url(config),
            headers=_airtable_headers(config["api_key"]),
            params=params,
            timeout=15,
        )

    for attempt in range(1, RETRY_COUNT + 1):
        try:
            response = await asyncio.to_thread(_get)

            if response.status_code == 200:
                records = response.json().get("records", [])
                if records:
                    print(f"  [INFO] Airtable record verified (attempt {attempt}/{RETRY_COUNT})")
                    return {"verified": True, "details": f"Found {len(records)} record(s)"}

                print(f"  [WARN] Record not found yet (attempt {attempt}/{RETRY_COUNT}), retrying...")

            else:
                print(f"  [WARN] Verification query failed (HTTP {response.status_code}), "
                      f"attempt {attempt}/{RETRY_COUNT}")

        except Exception as exc:
            print(f"  [WARN] Verification error on attempt {attempt}: {exc}")

        if attempt < RETRY_COUNT:
            await asyncio.sleep(RETRY_DELAY_S)

    print(f"  [ERROR] Airtable record not found after {RETRY_COUNT} attempts")
    return {"verified": False, "details": "Record not found after retries"}


# ─────────────────────────────────────────────────────────────
# Orchestrator — run all three layers in sequence
# ─────────────────────────────────────────────────────────────

async def run_airtable_checks(page: Page, config: dict, test_email: str) -> dict:
    """
    Run B1 → B2 → C in sequence and return a unified result.

    Args:
        page       : Active Playwright page (already on the domain).
        config     : Dict with api_key, base_id, table_name, domain.
        test_email : Unique e-mail used as the test record identifier.

    Returns:
        {
            "airtable_linked":   bool,
            "api_submission":    bool,
            "airtable_verified": bool,
        }
    """
    base_url = f"https://{config['domain']}"

    # B1 — JS linkage check
    b1 = await check_airtable_js_linkage(page, base_url)

    # B2 — Direct API submission
    b2 = await send_test_lead_to_airtable(config, test_email)

    # C — Verification (only meaningful if B2 succeeded)
    if b2["success"]:
        c = await verify_airtable_entry(config, test_email)
    else:
        print("  [WARN] Skipping record verification — API submission failed")
        c = {"verified": False, "details": "Skipped: B2 failed"}

    return {
        "airtable_linked":   b1["linked"],
        "api_submission":    b2["success"],
        "airtable_verified": c["verified"],
    }
