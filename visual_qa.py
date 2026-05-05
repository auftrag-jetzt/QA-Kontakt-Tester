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
import re
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
AIRTABLE_LEADS_CONFIG = {
    "api_key":    os.environ.get("AIRTABLE_LEADS_API_KEY", ""),
    "base_id":    os.environ.get("AIRTABLE_LEADS_BASE_ID", "appL4PpAWoTl3rEzE"),
    "table_name": os.environ.get("AIRTABLE_LEADS_TABLE", "Leads Partner"),
}

# ── Table B: Trigger source + QA result write-back ────────────────────────────
AIRTABLE_TRIGGER_CONFIG = {
    "api_key":         os.environ.get("AIRTABLE_TRIGGER_API_KEY", ""),
    "base_id":         os.environ.get("AIRTABLE_TRIGGER_BASE_ID", "apphwncsSpj5PTIFX"),
    "table_name":      os.environ.get("AIRTABLE_TRIGGER_TABLE", "EMD Websiten"),
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
    "airtable_error", "error",
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
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", domain.strip()).strip("_") or "screenshot"
    filename = output_dir / f"{safe_name}.png"
    await page.screenshot(path=str(filename), full_page=True)
    return filename


def _domain_to_urls(domain: str) -> tuple[str, str, str]:
    """Return (host, target_url, base_url) for bare domains or full page URLs."""
    raw = domain.strip()
    parsed = urlparse(raw if raw.startswith(("http://", "https://")) else f"https://{raw}")
    host = parsed.netloc or parsed.path.split("/", 1)[0]
    path = parsed.path if parsed.netloc else ""
    target_url = f"https://{host}{path if path != '/' else ''}"
    base_url = f"https://{host}"
    return host, target_url, base_url


# ─────────────────────────────────────────────────────────────
# Part B1 — Frontend JS / Airtable Linkage Check
# ─────────────────────────────────────────────────────────────

def _normalize_domain(d: str) -> str:
    return d.lower().replace("www.", "").strip().rstrip("/")


async def _check_airtable_js_linkage(page, base_url: str) -> dict:
    """
    B1: Search for any JS file on the site that contains Airtable config.
    Tries multiple common JS paths — no hardcoded filename required.
    If found, also tries to extract the Airtable token/base for extra validation.
    B1 failure alone does NOT cause FAIL — B2/C are the real proof.
    """
    domain = _normalize_domain(urlparse(base_url).netloc)

    # Try multiple possible JS file locations
    js_paths = [
        "/js/airtable-form-handler.js",
        "/js/airtable-form.js",
        "/js/airtable.js",
        "/js/form.js",
        "/js/contact.js",
        "/js/main.js",
        "/js/app.js",
        "/js/script.js",
    ]

    for js_path in js_paths:
        js_url = base_url.rstrip("/") + js_path
        try:
            response = await page.request.get(js_url)
            if response.status != 200:
                continue

            js_content = await response.text()
            js_content_lower = js_content.lower()

            # Must contain airtable reference to count
            if "airtable" not in js_content_lower:
                continue

            print(f"  [INFO] Airtable JS found at: {js_path}")

            # Try to extract base ID for extra info (optional)
            base_match = re.search(r'app[A-Za-z0-9]{14}', js_content)
            if base_match:
                print(f"  [INFO] Airtable base ID detected in JS: {base_match.group()}")

            return {"linked": True, "details": f"Airtable JS found at {js_path}"}

        except Exception:
            continue

    # B1 failed — not critical, B2/C will verify directly
    print(f"  [WARN] No Airtable JS file found — B2/C checks will verify directly")
    return {"linked": False, "details": "No Airtable JS found (B2/C will verify)"}


# ─────────────────────────────────────────────────────────────
# Part B2 — Direct Airtable API Submission
# ─────────────────────────────────────────────────────────────

def _airtable_headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _table_url(cfg: dict) -> str:
    return f"https://api.airtable.com/v0/{cfg['base_id']}/{cfg['table_name']}"


async def _get_table_fields(cfg: dict) -> list[dict]:
    """
    Fetch the actual Airtable fields so test data can be sent using
    compatible field names and field types.
    Returns Airtable field metadata dicts, or an empty list on failure.
    """
    url = f"https://api.airtable.com/v0/meta/bases/{cfg['base_id']}/tables"

    def _get():
        return requests.get(
            url,
            headers=_airtable_headers(cfg["api_key"]),
            timeout=15,
        )

    try:
        response = await asyncio.to_thread(_get)
        if response.status_code == 200:
            tables = response.json().get("tables", [])
            table_name = cfg.get("table_name", "")
            for table in tables:
                if table.get("name") == table_name:
                    return table.get("fields", [])
        print(
            f"  [WARN] Could not fetch table fields "
            f"(HTTP {response.status_code}) for base={cfg.get('base_id')} "
            f"table={cfg.get('table_name')}: {response.text[:120]}"
        )
    except Exception as exc:
        print(f"  [WARN] Could not fetch table fields: {exc}")

    return []


def _field_name(field) -> str:
    if isinstance(field, dict):
        return field.get("name", "")
    return str(field)


def _field_type(field) -> str:
    if isinstance(field, dict):
        return field.get("type", "")
    return ""


def _is_readonly_or_complex_field(field) -> bool:
    field_type = _field_type(field)
    return field_type in {
        "aiText",
        "autoNumber",
        "barcode",
        "button",
        "count",
        "createdBy",
        "createdTime",
        "externalSyncSource",
        "formula",
        "lastModifiedBy",
        "lastModifiedTime",
        "lookup",
        "multipleAttachments",
        "multipleLookupValues",
        "multipleRecordLinks",
        "rollup",
    }


def _coerce_airtable_value(field, value):
    """Return a value Airtable can parse for this field type, or None to skip."""
    if _is_readonly_or_complex_field(field):
        return None

    field_type = _field_type(field)

    if field_type == "url":
        text = str(value)
        if text.startswith(("http://", "https://")):
            return text
        return f"https://{text}"

    if field_type in ("", "singleLineText", "multilineText", "richText", "email", "phoneNumber"):
        return str(value)

    if field_type in ("number", "currency", "percent", "duration", "rating"):
        digits = re.sub(r"[^\d.]", "", str(value))
        if not digits:
            return None
        try:
            number = float(digits)
            return int(number) if number.is_integer() else number
        except ValueError:
            return None

    # Select/link/date/checkbox fields often have constrained schemas. They are
    # not required for this synthetic QA record, so skip them instead of guessing.
    return None


def _build_test_payload(table_fields: list, test_email: str, domain: str) -> dict:
    """
    Build a test record payload that matches the actual field metadata.
    Only writes fields Airtable can parse safely.
    """
    # Mapping: lowercase field name patterns → test values
    field_map = {
        # Name variations
        "name": "QA Test",
        "vorname": "QA",
        "nachname": "Test",
        "firma": "QA Test GmbH",
        "company": "QA Test GmbH",

        # Email variations
        "email": test_email,
        "e-mail": test_email,
        "mail": test_email,

        # Phone variations
        "telefon": "1234567890",
        "phone": "1234567890",
        "tel": "1234567890",
        "telefonnummer": "1234567890",

        # Message variations
        "nachricht": "Automated QA Test",
        "message": "Automated QA Test",
        "mitteilung": "Automated QA Test",
        "kommentar": "Automated QA Test",
        "beschreibung": "Automated QA Test",

        # Website/domain variations
        "website": domain,
        "webseite": domain,
        "url": domain,
        "domain": domain,

        # Address variations
        "adresse": "QA Teststraße 1",
        "address": "QA Teststraße 1",
        "straße": "QA Teststraße 1",
        "strasse": "QA Teststraße 1",

        # City variations
        "stadt": "Berlin",
        "city": "Berlin",
        "ort": "Berlin",

        # PLZ / ZIP
        "plz": "10115",
        "postleitzahl": "10115",
        "zip": "10115",
    }

    fields = {}
    for field in table_fields:
        field_name = _field_name(field)
        field_type = _field_type(field)
        field_lower = field_name.lower().strip()

        # Skip computed/readonly fields
        if field_lower in ("datum", "date", "created", "erstellt", "id") or _is_readonly_or_complex_field(field):
            continue

        for pattern, value in field_map.items():
            if pattern in field_lower:
                coerced = _coerce_airtable_value(field, value)
                if coerced is not None:
                    fields[field_name] = coerced
                elif field_type:
                    print(f"  [INFO] Skipping field '{field_name}' ({field_type}) - incompatible test value")
                break

    # Always ensure we have at least a name and some contact info
    if not fields:
        print(f"  [WARN] Could not map any fields, using fallback payload")
        fields = {"Name": "QA Test"}

    return fields


async def _send_test_lead_to_airtable(cfg: dict, test_email: str) -> dict:
    """
    POST a test record directly to Airtable REST API.
    Dynamically detects field names so it works with any website's table.
    """
    domain = cfg.get("domain", "qa-test.de")

    # Try to get actual field metadata from the table
    table_fields = await _get_table_fields(cfg)
    field_names = [_field_name(field) for field in table_fields]

    if table_fields:
        preview = [f"{_field_name(field)}:{_field_type(field) or 'unknown'}" for field in table_fields[:5]]
        print(f"  [INFO] Detected {len(table_fields)} fields in table: {preview}...")
        fields = _build_test_payload(table_fields, test_email, domain)
    else:
        # Fallback to common field names if metadata fetch failed
        print(f"  [WARN] Using fallback field names")
        fields = {
            "Name":      "QA Test",
            "E-Mail":    test_email,
            "Website":   domain,
            "Telefon":   "1234567890",
            "Nachricht": "Automated QA Test",
        }

    print(f"  [INFO] Submitting test record with fields: {list(fields.keys())}")

    payload = {"records": [{"fields": fields}]}

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
            return {
                "success": True,
                "record_id": record_id,
                "details": "Record created",
                "test_email": test_email,
                "field_names": field_names,
                "submitted_fields": list(fields.keys()),
            }

        print(f"  [ERROR] Airtable API failed (HTTP {response.status_code}): {response.text[:200]}")
        if response.status_code == 401:
            details = (
                "AIRTABLE_LEADS_API_KEY is missing/invalid in the QA webhook server, "
                f"or it is not a valid token for base {cfg.get('base_id')} "
                f"table {cfg.get('table_name')}"
            )
        else:
            details = f"HTTP {response.status_code}: {response.text[:100]}"
        return {
            "success": False,
            "record_id": None,
            "details": details,
            "field_names": field_names,
            "submitted_fields": list(fields.keys()),
        }

    except Exception as exc:
        print(f"  [ERROR] Airtable API exception: {exc}")
        return {
            "success": False,
            "record_id": None,
            "details": str(exc),
            "field_names": field_names,
            "submitted_fields": list(fields.keys()),
        }


# ─────────────────────────────────────────────────────────────
# Part C — Airtable Record Verification
# ─────────────────────────────────────────────────────────────

async def _verify_airtable_entry(
    cfg: dict,
    test_email: str,
    record_id: str = None,
    field_names: list[str] = None,
) -> dict:
    """
    Poll Airtable to confirm the test record exists.
    Tries multiple email field name variations since field names differ per website.
    """
    if record_id:
        def _get_record():
            return requests.get(
                f"{_table_url(cfg)}/{record_id}",
                headers=_airtable_headers(cfg["api_key"]),
                timeout=15,
            )

        try:
            response = await asyncio.to_thread(_get_record)
            if response.status_code == 200:
                print(f"  [INFO] Airtable record verified by ID: {record_id}")
                return {"verified": True, "details": f"Record {record_id} readable by ID"}
            print(f"  [WARN] Record ID verification failed (HTTP {response.status_code}): {response.text[:120]}")
        except Exception as exc:
            print(f"  [WARN] Record ID verification error: {exc}")

    # Try exact detected e-mail fields first, then common fallbacks.
    email_field_variants = []
    for field_name in field_names or []:
        field_lower = field_name.lower()
        if ("mail" in field_lower or "email" in field_lower) and field_name not in email_field_variants:
            email_field_variants.append(field_name)
    for fallback in ["E-Mail", "Email", "email", "e-mail", "Mail", "mail"]:
        if fallback not in email_field_variants:
            email_field_variants.append(fallback)
    safe_email = test_email.replace('"', '\\"')

    def _get(filter_formula):
        return requests.get(
            _table_url(cfg),
            headers=_airtable_headers(cfg["api_key"]),
            params={"filterByFormula": filter_formula},
            timeout=15,
        )

    for attempt in range(1, _AT_RETRY_COUNT + 1):
        # Try each email field name variant
        for email_field in email_field_variants:
            try:
                filter_formula = f'FIND("{safe_email}", {{{email_field}}})'
                response = await asyncio.to_thread(_get, filter_formula)

                if response.status_code == 200:
                    records = response.json().get("records", [])
                    if records:
                        print(f"  [INFO] Airtable record verified via field '{email_field}' (attempt {attempt})")
                        return {"verified": True, "details": f"Found {len(records)} record(s)"}
                elif response.status_code == 422:
                    # Field doesn't exist — try next variant
                    continue

            except Exception as exc:
                print(f"  [WARN] Verification error with field '{email_field}': {exc}")
                continue

        print(f"  [WARN] Record not found yet (attempt {attempt}/{_AT_RETRY_COUNT}), retrying...")
        if attempt < _AT_RETRY_COUNT:
            await asyncio.sleep(_AT_RETRY_DELAY)

    print(f"  [ERROR] Airtable record not found after {_AT_RETRY_COUNT} attempts")
    return {"verified": False, "details": "Record not found after retries"}


# ─────────────────────────────────────────────────────────────
# Write-back — update the triggering Airtable record with QA result
# ─────────────────────────────────────────────────────────────

def _map_status_to_airtable(internal_status: str) -> str:
    """
    Map internal QA status to Airtable field value.
    Internal: PASS, PARTIAL, FAIL → Airtable: passed, failed
    """
    if internal_status == "PASS":
        return "passed"
    return "failed"  # PARTIAL and FAIL both map to failed


def write_qa_result_to_airtable(record_id: str, status: str, cfg: dict = None, error_msg: str = "") -> bool:
    """
    PATCH the Airtable record that triggered this QA run with the final verdict.
    """
    if cfg is None:
        cfg = AIRTABLE_TRIGGER_CONFIG

    field = cfg.get("qa_result_field")
    if not field:
        print("  [INFO] Write-back skipped (qa_result_field is not configured)")
        return False

    airtable_status = _map_status_to_airtable(status)
    url = f"https://api.airtable.com/v0/{cfg['base_id']}/{cfg['table_name']}/{record_id}"

    payload = {"fields": {field: airtable_status}}

    error_field = cfg.get("error_field")
    if error_field:
        # Always write error field — clear it on pass, set it on fail
        payload["fields"][error_field] = error_msg[:500] if error_msg else ""

    try:
        response = requests.patch(
            url,
            headers=_airtable_headers(cfg["api_key"]),
            json=payload,
            timeout=15,
        )
        if response.status_code == 200:
            print(f"  [INFO] Write-back OK: record {record_id} → {airtable_status}")
            return True
        print(f"  [ERROR] Write-back failed (HTTP {response.status_code}): {response.text[:200]}")
        return False
    except Exception as exc:
        print(f"  [ERROR] Write-back exception: {exc}")
        return False


def set_status_to_testing(record_id: str, cfg: dict = None) -> bool:
    """
    Set Airtable record status to 'testing' immediately when QA starts.
    Prevents duplicate triggers.
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
        c = await _verify_airtable_entry(
            cfg,
            test_email,
            record_id=b2.get("record_id"),
            field_names=b2.get("field_names"),
        )
    else:
        print("  [WARN] Skipping record verification — API submission failed")
        c = {"verified": False, "details": "Skipped: B2 failed"}

    return {
        "airtable_linked":   b1["linked"],
        "api_submission":    b2["success"],
        "airtable_verified": c["verified"],
        "b1_details":        b1.get("details", ""),
        "b2_details":        b2.get("details", ""),
        "c_details":         c.get("details", ""),
        "record_id":         b2.get("record_id"),
    }


# ─────────────────────────────────────────────────────────────
# Per-Domain Runner
# ─────────────────────────────────────────────────────────────

async def process_domain(browser, domain: str, output_dir: Path, run_id: str) -> dict:
    """
    Open the domain, wait for load, take screenshot, run Gemini analysis,
    attempt contact form submission, then run Airtable checks (B1/B2/C).
    """
    host, url, _ = _domain_to_urls(domain)
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
        "airtable_error":    "",
        "error":             "",
    }

    context = None
    try:
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
        at_cfg = {**AIRTABLE_LEADS_CONFIG, "domain": host}
        airtable_enabled = bool(at_cfg["api_key"] and at_cfg["base_id"])
        airtable_details = {}

        if airtable_enabled:
            print(f"  >> Running Airtable checks (B1 / B2 / C)...")
            test_email = f"qa+{run_id}@test.com"
            at = await _run_airtable_checks(page, at_cfg, test_email)
            airtable_details = at
            result["airtable_linked"]   = at["airtable_linked"]
            result["api_submission"]    = at["api_submission"]
            result["airtable_verified"] = at["airtable_verified"]
        else:
            print(f"  -- Airtable checks skipped (AIRTABLE_LEADS_API_KEY not set)")

        # ── Final status ──────────────────────────────────────
        # B1 (JS check) is informational only — does not affect final status
        # B2 + C are the real Airtable verification
        ui_ok = gemini_ok and form_ok

        if not airtable_enabled:
            # No Airtable creds — judge by UI only
            final = "PASS" if ui_ok else "FAIL"

        elif ui_ok and result["api_submission"] and result["airtable_verified"]:
            # Full pass: API submission worked AND record verified
            final = "PASS"

        elif ui_ok and result["api_submission"]:
            # Submitted but couldn't verify — partial
            final = "PARTIAL"

        elif ui_ok:
            # UI ok but Airtable submission failed — partial
            final = "PARTIAL"

        else:
            # Everything failed
            final = "FAIL"

        result["status"] = final

        if final == "PASS":
            result["error"] = ""
            result["form_error"] = ""
            result["airtable_error"] = ""

        elif not result["error"]:
            reasons = []
            if result["gemini_status"] not in ("PASS", "SKIPPED"):
                reasons.append(f"Gemini {result['gemini_status']}: {result['gemini_issues']}")
            if result["form_status"] != "PASS" and result["form_error"]:
                reasons.append(f"Form failed: {result['form_error']}")
            if airtable_enabled:
                if not result["api_submission"]:
                    reasons.append(f"Airtable API submission failed: {airtable_details.get('b2_details', 'no details')}")
                elif not result["airtable_verified"]:
                    reasons.append(f"Airtable verification failed: {airtable_details.get('c_details', 'no details')}")
            if reasons:
                result["error"] = " | ".join(reasons)[:500]
                result["airtable_error"] = result["error"]

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
        if result["status"] == "PASS":
            error_msg = ""
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
