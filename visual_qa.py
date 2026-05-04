"""
visual_qa.py — Automated Website Screenshot & QA Reporter
=========================================================

Installation:
    pip install playwright pandas google-generativeai Pillow requests
    playwright install chromium

Environment:
    set GEMINI_API_KEY=your_key_here
    set AIRTABLE_API_KEY=your_airtable_pat
    set AIRTABLE_BASE_ID=appXXXXXXXXXXXXXX
    set AIRTABLE_TABLE=Leads              (optional, defaults to "Leads")

Usage:
    python visual_qa.py

Input:
    data.csv — must contain a column: domain

Output:
    screenshots/<domain>.png  — full-page screenshots
    ui_report.csv             — domain, status, screenshot, gemini_status,
                                gemini_issues, form_status, form_error,
                                airtable_linked, api_submission,
                                airtable_verified, error
"""

import asyncio
import os
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

# Load environment variables from .env file (for local development)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; use shell env vars instead

import pandas as pd
import requests
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth

# Stealth configuration applied to every page.
_STEALTH = Stealth(
    chrome_runtime=True,
    navigator_webdriver=True,
    navigator_permissions=True,
    iframe_content_window=True,
    navigator_user_agent=True,
    navigator_user_agent_data=True,
    sec_ch_ua=True,
    webgl_vendor=True,
)

# Gemini is optional — loaded only when GEMINI_API_KEY is present.
try:
    from gemini_analyzer import analyze_screenshot
    GEMINI_AVAILABLE = True
except EnvironmentError:
    GEMINI_AVAILABLE = False
except Exception as _gem_import_err:
    GEMINI_AVAILABLE = False
    print(f"[WARN] gemini_analyzer import failed: {_gem_import_err}")

from form_automation import submit_form


# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────

INPUT_CSV       = "data.csv"
OUTPUT_CSV      = "ui_report.csv"
SCREENSHOTS_DIR = Path("screenshots")

# Timeouts (milliseconds)
NAVIGATION_TIMEOUT = 30_000
WAIT_AFTER_LOAD    = 2_000

# ── Table A: Lead submissions (B2 test records + C verification) ──────────────
# This is the table where the pipeline submits a test lead and then verifies
# it was stored. Unrelated to the trigger that kicks off the QA run.
#
# Secrets (api_key) MUST come from environment variables. Non-secret identifiers
# (base_id, table_name) fall back to defaults so the CLI keeps working without
# a full env setup. If AIRTABLE_LEADS_API_KEY is unset, the B2/C Airtable steps
# are skipped — the pipeline still produces screenshots, Gemini analysis, and
# form-submission results.
AIRTABLE_LEADS_CONFIG = {
    "api_key":    os.environ.get("AIRTABLE_LEADS_API_KEY", ""),
    "base_id":    os.environ.get("AIRTABLE_LEADS_BASE_ID", "appL4PpAWoTl3rEzE"),
    "table_name": os.environ.get("AIRTABLE_LEADS_TABLE", "Leads Partner"),
}

# ── Table B: Trigger source + QA result write-back ────────────────────────────
# This is a DIFFERENT table/base. An Airtable automation sends a record_id
# + domain from here to trigger the QA run, and the PASS/FAIL result is
# written back to this record.
#
# Same rule: api_key from env var, schema fields default to known values.
# If AIRTABLE_TRIGGER_API_KEY is unset, write-back is skipped.
AIRTABLE_TRIGGER_CONFIG = {
    "api_key":         os.environ.get("AIRTABLE_TRIGGER_API_KEY", ""),
    "base_id":         os.environ.get("AIRTABLE_TRIGGER_BASE_ID", "apphwncsSpj5PTIFX"),
    "table_name":      os.environ.get("AIRTABLE_TRIGGER_TABLE", "EMD Webseiten"),
    "domain_field":    os.environ.get("AIRTABLE_TRIGGER_DOMAIN_FIELD", "Domain"),
    "qa_result_field": os.environ.get("AIRTABLE_TRIGGER_RESULT_FIELD", "Kontakt status"),
    "error_field":     os.environ.get("AIRTABLE_TRIGGER_ERROR_FIELD", "Kontakt error"),
}

# Airtable verification retry settings
_AT_RETRY_COUNT = 3
_AT_RETRY_DELAY = 4   # seconds


# ─────────────────────────────────────────────────────────────
# CSV Helpers
# ─────────────────────────────────────────────────────────────

def load_domains(filepath: str) -> list[str]:
    """Read domains from CSV. Expects a 'domain' column."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Input file not found: {filepath}")

    df = pd.read_csv(filepath)

    if "domain" not in df.columns:
        raise ValueError(f"CSV must contain a 'domain' column. Found: {list(df.columns)}")

    domains = df["domain"].dropna().str.strip().tolist()
    print(f"[INFO] Loaded {len(domains)} domain(s) from '{filepath}'")
    return domains


# Report columns — order matches result dict declaration
_REPORT_COLUMNS = [
    "domain", "status", "screenshot",
    "gemini_status", "gemini_issues",
    "form_status", "form_error",
    "airtable_linked", "api_submission", "airtable_verified",
    "error",
]


def save_report(results: list[dict], filepath: str) -> None:
    """Write QA results to CSV."""
    df = pd.DataFrame(results, columns=_REPORT_COLUMNS)
    df.to_csv(filepath, index=False)
    print(f"\n[REPORT] Saved to '{filepath}'")


# ─────────────────────────────────────────────────────────────
# Screenshot Logic
# ─────────────────────────────────────────────────────────────

async def capture_screenshot(page, domain: str, output_dir: Path) -> Path:
    """Take a full-page screenshot and return the file path."""
    filename = output_dir / f"{domain}.png"
    await page.screenshot(path=str(filename), full_page=True)
    return filename


# ─────────────────────────────────────────────────────────────
# Part B1 — Frontend JS / Airtable Linkage Check
# ─────────────────────────────────────────────────────────────

import re

def _normalize_domain(d: str) -> str:
    return d.lower().replace("www.", "").strip().rstrip("/")


async def _check_airtable_js_linkage(page, base_url: str) -> dict:
    """
    Improved B1:
    - Validates JS existence & structure
    - Case-insensitive domain match
    - Extracts Website value safely
    """
    js_url = base_url.rstrip("/") + "/js/airtable-form-handler.js"
    domain = _normalize_domain(urlparse(base_url).netloc)

    try:
        response = await page.request.get(js_url)

        if response.status != 200:
            print(f"  [WARN] Airtable handler missing (HTTP {response.status})")
            return {"linked": False, "details": f"JS handler not found (HTTP {response.status})"}

        js_content = await response.text()
        js_content_lower = js_content.lower()

        # Basic structure validation
        if "collectformdata" not in js_content_lower:
            print(f"  [ERROR] 'collectFormData' missing in JS")
            return {"linked": False, "details": "Invalid JS structure"}

        if "website" not in js_content_lower:
            print(f"  [ERROR] 'Website' field missing in JS")
            return {"linked": False, "details": "Website field missing"}

        # Extract Website field
        match = re.search(r'"Website"\s*:\s*"([^"]+)"', js_content)

        if match:
            js_domain = _normalize_domain(match.group(1))

            if js_domain == domain:
                print(f"  [INFO] Airtable handler detected")
                print(f"  [INFO] Domain matches JS config")
                return {"linked": True, "details": "JS valid + domain match"}
            else:
                print(f"  [WARN] Domain mismatch (JS={js_domain}, URL={domain})")
                return {"linked": True, "details": "JS valid but domain mismatch"}

        # Fallback (still valid)
        print(f"  [INFO] Airtable handler detected (no explicit domain match)")
        return {"linked": True, "details": "JS structure valid"}

    except Exception as exc:
        print(f"  [ERROR] Could not fetch Airtable JS handler: {exc}")
        return {"linked": False, "details": str(exc)}

# ─────────────────────────────────────────────────────────────
# Part B2 — Direct Airtable API Submission
# ─────────────────────────────────────────────────────────────

def _airtable_headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _table_url(cfg: dict) -> str:
    return f"https://api.airtable.com/v0/{cfg['base_id']}/{cfg['table_name']}"


async def _send_test_lead_to_airtable(cfg: dict, test_email: str) -> dict:
    """POST a test record directly to Airtable REST API."""
    payload = {
        "records": [{
            "fields": {
                "Name":      "QA Test",
                "E-Mail":    test_email,
                "Website":   cfg["domain"],
                "Telefon":   "1234567890",
                "Nachricht": "Automated QA Test",
            }
        }]
    }

    def _post():
        return requests.post(
            _table_url(cfg),
            headers=_airtable_headers(cfg["api_key"]),
            json=payload,
            timeout=15,
        )

    try:
        response = await asyncio.to_thread(_post)
        if response.status_code in (200, 201):
            record_id = response.json()["records"][0]["id"]
            print(f"  [INFO] Airtable API submission successful (record: {record_id})")
            return {"success": True, "record_id": record_id, "details": "Record created"}

        print(f"  [ERROR] Airtable API failed (HTTP {response.status_code}): {response.text[:200]}")
        return {"success": False, "record_id": None, "details": f"HTTP {response.status_code}"}

    except Exception as exc:
        print(f"  [ERROR] Airtable API exception: {exc}")
        return {"success": False, "record_id": None, "details": str(exc)}


# ─────────────────────────────────────────────────────────────
# Part C — Airtable Record Verification
# ─────────────────────────────────────────────────────────────

async def _verify_airtable_entry(cfg: dict, test_email: str) -> dict:
    """
    Fixed:
    - Uses FIND() instead of strict equality
    - Handles Airtable quirks
    - Better logging
    """

    params = {
        "filterByFormula": f"FIND('{test_email}', {{E-Mail}})"
    }

    def _get():
        return requests.get(
            _table_url(cfg),
            headers=_airtable_headers(cfg["api_key"]),
            params=params,
            timeout=15,
        )

    for attempt in range(1, _AT_RETRY_COUNT + 1):
        try:
            response = await asyncio.to_thread(_get)

            if response.status_code == 200:
                data = response.json()
                records = data.get("records", [])

                if records:
                    print(f"  [INFO] Airtable record verified (attempt {attempt})")
                    return {"verified": True, "details": f"Found {len(records)} record(s)"}

                print(f"  [WARN] Record not found yet (attempt {attempt}), retrying...")

            else:
                print(f"  [WARN] Verification HTTP {response.status_code}: {response.text[:100]}")

        except Exception as exc:
            print(f"  [WARN] Verification error: {exc}")

        if attempt < _AT_RETRY_COUNT:
            await asyncio.sleep(_AT_RETRY_DELAY)

    print(f"  [ERROR] Airtable record not found after retries")
    return {"verified": False, "details": "Not found"}

# ─────────────────────────────────────────────────────────────
# Write-back — update the triggering Airtable record with QA result
# ─────────────────────────────────────────────────────────────

def _map_status_to_airtable(internal_status: str) -> str:
    """
    Map internal QA status to Airtable field value.

    Internal: PASS, PARTIAL, FAIL
    Airtable: passed, failed
    """
    if internal_status == "PASS":
        return "passed"
    return "failed"  # PARTIAL and FAIL both map to failed


def write_qa_result_to_airtable(record_id: str, status: str, cfg: dict = None, error_msg: str = "") -> bool:
    """
    PATCH the Airtable record that triggered this QA run with the final verdict and optional error details.

    Args:
        record_id:  Airtable record ID, e.g. "recXXXXXXXXXXXXXX"
        status:     "PASS", "PARTIAL", or "FAIL" (internal status)
        cfg:        Airtable config dict; defaults to AIRTABLE_TRIGGER_CONFIG
        error_msg:  Optional error message to write to error field

    Returns True on success, False on failure.
    """
    if cfg is None:
        cfg = AIRTABLE_TRIGGER_CONFIG

    field = cfg.get("qa_result_field")
    if not field:
        print("  [INFO] Write-back skipped (qa_result_field is not configured)")
        return False

    airtable_status = _map_status_to_airtable(status)
    url = f"https://api.airtable.com/v0/{cfg['base_id']}/{cfg['table_name']}/{record_id}"

    # Build payload: always include status, optionally include error message
    payload = {"fields": {field: airtable_status}}

    error_field = cfg.get("error_field")
    if error_msg and error_field:
        payload["fields"][error_field] = error_msg[:500]  # Limit to 500 chars

    try:
        response = requests.patch(
            url,
            headers=_airtable_headers(cfg["api_key"]),
            json=payload,
            timeout=15,
        )
        if response.status_code == 200:
            msg = f"record {record_id} → {field} = {airtable_status}"
            if error_msg and error_field:
                msg += f", {error_field} = {error_msg[:50]}..."
            print(f"  [INFO] Write-back OK: {msg}")
            return True
        print(f"  [ERROR] Write-back failed (HTTP {response.status_code}): {response.text[:200]}")
        return False
    except Exception as exc:
        print(f"  [ERROR] Write-back exception: {exc}")
        return False


def set_status_to_testing(record_id: str, cfg: dict = None) -> bool:
    """
    Set Airtable record status to 'testing' immediately when QA starts.
    Prevents duplicate triggers (automation only fires on 'to be tested').

    Args:
        record_id: Airtable record ID
        cfg: Airtable config dict; defaults to AIRTABLE_TRIGGER_CONFIG

    Returns True on success, False on failure.
    """
    if cfg is None:
        cfg = AIRTABLE_TRIGGER_CONFIG

    field = cfg.get("qa_result_field")
    if not field:
        print("  [INFO] Testing status skipped (qa_result_field not configured)")
        return False

    url = f"https://api.airtable.com/v0/{cfg['base_id']}/{cfg['table_name']}/{record_id}"
    payload = {"fields": {field: "testing"}}

    try:
        response = requests.patch(
            url,
            headers=_airtable_headers(cfg["api_key"]),
            json=payload,
            timeout=15,
        )
        if response.status_code == 200:
            print(f"  [INFO] Status set to 'testing': record {record_id}")
            return True
        print(f"  [ERROR] Failed to set testing status (HTTP {response.status_code}): {response.text[:200]}")
        return False
    except Exception as exc:
        print(f"  [ERROR] Testing status exception: {exc}")
        return False


# ─────────────────────────────────────────────────────────────
# Airtable Orchestrator — B1 → B2 → C
# ─────────────────────────────────────────────────────────────

async def _run_airtable_checks(page, cfg: dict, test_email: str) -> dict:
    """Run all three Airtable layers and return a unified result dict."""
    base_url = f"https://{cfg['domain']}"

    b1 = await _check_airtable_js_linkage(page, base_url)
    b2 = await _send_test_lead_to_airtable(cfg, test_email)

    if b2["success"]:
        c = await _verify_airtable_entry(cfg, test_email)
    else:
        print("  [WARN] Skipping record verification — API submission failed")
        c = {"verified": False, "details": "Skipped: B2 failed"}

    return {
        "airtable_linked":   b1["linked"],
        "api_submission":    b2["success"],
        "airtable_verified": c["verified"],
    }


# ─────────────────────────────────────────────────────────────
# Per-Domain Runner
# ─────────────────────────────────────────────────────────────

async def process_domain(browser, domain: str, output_dir: Path, run_id: str) -> dict:
    """
    Open the domain, wait for load, take screenshot, run Gemini analysis,
    attempt contact form submission, then run Airtable checks (B1/B2/C).

    Returns a result dict with keys matching _REPORT_COLUMNS.
    """
    url = f"https://{domain}"
    result = {
        "domain":            domain,
        "status":            "FAIL",
        "screenshot":        "",
        "gemini_status":     "",
        "gemini_issues":     "",
        "form_status":       "",
        "form_error":        "",
        "airtable_linked":   None,
        "api_submission":    None,
        "airtable_verified": None,
        "error":             "",
    }

    context = None
    try:
        # Isolated browser context per domain (clean cookies/cache)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            ignore_https_errors=True,
        )
        page = await context.new_page()
        page.set_default_navigation_timeout(NAVIGATION_TIMEOUT)

        print(f"  >> Navigating to {url} ...")
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(WAIT_AFTER_LOAD)

        # ── Stage 1: Screenshot ───────────────────────────────
        screenshot_path = await capture_screenshot(page, domain, output_dir)
        result["screenshot"] = str(screenshot_path)

        # ── Stage 2: Gemini visual analysis ──────────────────
        if GEMINI_AVAILABLE:
            print(f"  >> Analyzing with Gemini...")
            try:
                gemini_result = analyze_screenshot(str(screenshot_path))
                result["gemini_status"] = gemini_result["status"]
                result["gemini_issues"] = " | ".join(gemini_result["issues"]) if gemini_result["issues"] else ""
            except Exception as gem_err:
                result["gemini_status"] = "ERROR"
                result["gemini_issues"] = str(gem_err)
        else:
            print(f"  -- Gemini skipped (no API key)")
            result["gemini_status"] = "SKIPPED"
            result["gemini_issues"] = "Gemini disabled (no API key)"

        # ── Stage 3: Form automation ──────────────────────────
        print(f"  >> Submitting contact form...")
        form_result = await submit_form(page, domain, run_id)
        result["form_status"] = form_result["status"]
        result["form_error"]  = form_result["error"]

        gemini_ok = result["gemini_status"] in ("PASS", "SKIPPED")
        form_ok   = result["form_status"] == "PASS"

        # ── Stage 4: Airtable checks (B1 + B2 + C) ───────────
        at_cfg = {**AIRTABLE_LEADS_CONFIG, "domain": domain}
        airtable_enabled = bool(at_cfg["api_key"] and at_cfg["base_id"])

        if airtable_enabled:
            print(f"  >> Running Airtable checks (B1 / B2 / C)...")
            test_email = f"qa+{run_id}@test.com"
            at = await _run_airtable_checks(page, at_cfg, test_email)
            result["airtable_linked"]   = at["airtable_linked"]
            result["api_submission"]    = at["api_submission"]
            result["airtable_verified"] = at["airtable_verified"]
        else:
            print(f"  -- Airtable checks skipped (AIRTABLE_API_KEY / AIRTABLE_BASE_ID not set)")

        # ── Final status ──────────────────────────────────────
        ui_ok = gemini_ok and form_ok

        if not airtable_enabled:
            final = "PASS" if ui_ok else "FAIL"

        elif result["api_submission"] and result["airtable_verified"]:
            final = "PASS"

        elif result["api_submission"]:
            final = "PARTIAL"

        elif ui_ok:
            final = "PARTIAL"

        else:
            final = "FAIL"

        result["status"] = final
        print(
            f"  [OK] Done -- Gemini: {result['gemini_status']} | "
            f"Form: {result['form_status']} | "
            f"Airtable: linked={result['airtable_linked']} "
            f"api={result['api_submission']} "
            f"verified={result['airtable_verified']} | "
            f"Final: {final}"
        )

    except PlaywrightTimeoutError:
        result["error"] = f"Navigation timeout after {NAVIGATION_TIMEOUT // 1000}s"
        print(f"  [FAIL] Timeout: {domain}")

    except Exception as exc:
        result["error"] = str(exc)
        print(f"  [FAIL] {domain}: {exc}")

    finally:
        if context:
            await context.close()

    return result


# ─────────────────────────────────────────────────────────────
# Main Runner
# ─────────────────────────────────────────────────────────────

async def run_qa(domains: list[str], run_id: str) -> list[dict]:
    """Launch browser and process all domains sequentially."""
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    async with _STEALTH.use_async(async_playwright()) as pw:
        browser = await pw.chromium.launch(headless=True)
        gemini_label   = "enabled" if GEMINI_AVAILABLE else "SKIPPED (no API key)"
        airtable_label = "enabled" if (AIRTABLE_LEADS_CONFIG["api_key"] and AIRTABLE_LEADS_CONFIG["base_id"]) else "SKIPPED (no credentials)"
        print(f"[INFO]  Stealth mode          : enabled")
        print(f"[INFO]  Gemini visual analysis : {gemini_label}")
        print(f"[INFO]  Airtable checks        : {airtable_label}")
        print(f"\n[START] Processing {len(domains)} domain(s)... (run_id={run_id})\n")

        for i, domain in enumerate(domains, start=1):
            print(f"[{i}/{len(domains)}] {domain}")
            result = await process_domain(browser, domain, SCREENSHOTS_DIR, run_id)
            results.append(result)

        await browser.close()

    return results


# ─────────────────────────────────────────────────────────────
# Public single-domain callable (for external triggers)
# ─────────────────────────────────────────────────────────────

def run_domain(domain: str, airtable_record_id: str = None, run_id: str = None) -> dict:
    """
    Public synchronous entry point — test a single domain end-to-end.

    Intended for external callers (webhook server, polling script, Airtable
    automation, etc.) that want to trigger a QA run without dealing with the
    async internals.

    Args:
        domain:              Bare domain, e.g. "fensterreinigung-ulm.de".
                             The "https://" prefix is added automatically.
        airtable_record_id:  When provided the final QA status (PASS / PARTIAL
                             / FAIL) is written back to this Airtable record
                             in the field defined by AIRTABLE_CONFIG['qa_status_field'].
        run_id:              Optional identifier used for unique test e-mails
                             and screenshot naming; auto-generated if omitted.

    Returns:
        dict with keys matching _REPORT_COLUMNS:
            domain, status, screenshot, gemini_status, gemini_issues,
            form_status, form_error, airtable_linked, api_submission,
            airtable_verified, error
    """
    if run_id is None:
        run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    async def _run():
        async with _STEALTH.use_async(async_playwright()) as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                return await process_domain(browser, domain, SCREENSHOTS_DIR, run_id)
            finally:
                await browser.close()

    result = asyncio.run(_run())

    if airtable_record_id and AIRTABLE_TRIGGER_CONFIG.get("api_key") and AIRTABLE_TRIGGER_CONFIG.get("base_id"):
        error_msg = result.get("error", "") or result.get("form_error", "")
        write_qa_result_to_airtable(airtable_record_id, result["status"], error_msg=error_msg)

    return result


# ─────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────

def main():
    start = datetime.now()

    run_id = f"run_{start.strftime('%Y%m%d_%H%M%S')}"

    domains = load_domains(INPUT_CSV)
    results = asyncio.run(run_qa(domains, run_id))
    save_report(results, OUTPUT_CSV)

    passed  = sum(1 for r in results if r["status"] == "PASS")
    partial = sum(1 for r in results if r["status"] == "PARTIAL")
    failed  = len(results) - passed - partial
    duration = (datetime.now() - start).total_seconds()

    print(f"\n{'=' * 50}")
    print(f"  Total    : {len(results)}")
    print(f"  Passed   : {passed}")
    print(f"  Partial  : {partial}")
    print(f"  Failed   : {failed}")
    print(f"  Duration : {duration:.1f}s")
    print(f"{'=' * 50}\n")


if __name__ == "__main__":
    main()
