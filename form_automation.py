"""
form_automation.py — Contact Form Automation Module
====================================================

Navigates to the contact section of a website, optionally switches
to the "Serviceanfrage" tab, fills the form with test data, and submits.

These sites are German cleaning service websites, so selectors target
both German and English field names/labels.

Usage:
    from form_automation import submit_form

    result = await submit_form(page, "example.de", "run_20240409_001")
    # {"status": "PASS", "error": ""}
"""

import re
from urllib.parse import urlparse

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError


# ─────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────

# Test data injected into every form
TEST_DATA = {
    "company": "QA Automation GmbH",
    "name":    "Test User",
    "email":   "qa@test.com",
    "phone":   "+491234567890",
}

# Timeouts
SHORT_TIMEOUT = 3_000   # ms — for optional elements (tabs, selectors)
FILL_TIMEOUT  = 2_000   # ms — for individual field visibility check

# Keywords to identify the contact link in navigation
_CONTACT_RE = re.compile(
    r"kontakt|contact|anfrage|angebot|offerte|schreib|reach|touch|get.in",
    re.IGNORECASE,
)

# Keywords for the Serviceanfrage tab
_SERVICE_RE = re.compile(r"serviceanfrage|anfrage|service request", re.IGNORECASE)

# Common URL paths to try if nav click fails — includes .html variants
_CONTACT_PATHS = [
    "/kontakt.html",
    "/kontakt",
    "/kontakt/",
    "/contact.html",
    "/contact",
    "/contact/",
    "/anfrage.html",
    "/anfrage",
    "/anfrage/",
    "/angebot.html",
    "/angebot",
    "/impressum.html",  # some small sites put contact in impressum
]


# ─────────────────────────────────────────────────────────────
# Internal Helpers
# ─────────────────────────────────────────────────────────────

def _base_url_from_domain(domain: str) -> str:
    """Return scheme + host even when Airtable sends a full page URL."""
    raw = domain.strip()
    parsed = urlparse(raw if raw.startswith(("http://", "https://")) else f"https://{raw}")
    host = parsed.netloc or parsed.path.split("/", 1)[0]
    return f"https://{host}"


async def _navigate_to_contact(page: Page, base_url: str) -> bool:
    """
    Attempt to reach the contact section via four strategies:
      1. Click a navigation link containing contact keywords
      2. Navigate directly to known contact URL paths
      3. Scroll to an in-page #kontakt / #contact anchor
      4. Check if already on a contact page (domain included /kontakt etc.)
    Returns True if any strategy succeeded.
    """
    # Strategy 0 — check if we're already on a contact page
    current_url = page.url.lower()
    contact_indicators = ["kontakt", "contact", "anfrage", "angebot"]
    if any(kw in current_url for kw in contact_indicators):
        print(f"  [INFO] Already on contact page: {current_url}")
        return True

    # Strategy 1 — click nav link
    try:
        link = page.get_by_role("link", name=_CONTACT_RE).first
        if await link.is_visible(timeout=SHORT_TIMEOUT):
            await link.click()
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(1_000)
            print(f"  [INFO] Navigated via nav link click")
            return True
    except Exception:
        pass

    # Strategy 2 — direct URL navigation
    for path in _CONTACT_PATHS:
        try:
            response = await page.goto(
                base_url.rstrip("/") + path,
                wait_until="domcontentloaded",
                timeout=10_000,
            )
            if response and response.status < 400:
                # Verify there's actually a form on this page
                await page.wait_for_timeout(1_000)
                form_count = await page.locator("form, input[type='email'], textarea").count()
                if form_count > 0:
                    print(f"  [INFO] Found contact form at: {path}")
                    return True
        except Exception:
            continue

    # Strategy 3 — in-page anchor scroll
    try:
        section = page.locator(
            "#kontakt, #contact, #anfrage, #angebot, "
            "[id*='kontakt'], [id*='contact'], [id*='anfrage'], "
            "[class*='kontakt'], [class*='contact-form']"
        ).first
        count = await section.count()
        if count > 0:
            await section.scroll_into_view_if_needed()
            await page.wait_for_timeout(500)
            print(f"  [INFO] Scrolled to contact anchor on page")
            return True
    except Exception:
        pass

    # Strategy 4 — look for any form with email field on current page
    try:
        email_input = page.locator("input[type='email'], input[name*='email' i], input[name*='mail' i]").first
        count = await email_input.count()
        if count > 0:
            await email_input.scroll_into_view_if_needed()
            print(f"  [INFO] Found email input on current page")
            return True
    except Exception:
        pass

    return False


async def _switch_to_serviceanfrage(page: Page) -> None:
    """
    Click the 'Serviceanfrage' tab/button if present.
    Silently skips if not found — tab is optional.
    """
    try:
        tab = page.get_by_role("tab", name=_SERVICE_RE).first
        if not await tab.is_visible(timeout=SHORT_TIMEOUT):
            tab = page.get_by_role("button", name=_SERVICE_RE).first
        if not await tab.is_visible(timeout=SHORT_TIMEOUT):
            tab = page.get_by_text(_SERVICE_RE).first

        if await tab.is_visible(timeout=SHORT_TIMEOUT):
            await tab.click()
            await page.wait_for_timeout(1_000)
    except Exception:
        pass


async def _fill_field(page: Page, selectors: list[str], value: str) -> bool:
    """
    Try each selector in order until one is visible and fillable.
    Returns True if the field was filled, False if all selectors failed.
    """
    for selector in selectors:
        try:
            el = page.locator(selector).first
            if await el.is_visible(timeout=FILL_TIMEOUT):
                await el.fill(value)
                return True
        except Exception:
            continue
    return False


async def _fill_form(page: Page, message: str) -> dict[str, bool]:
    """
    Fill all form fields using multi-strategy selectors.
    Returns a dict of field → was_filled for diagnostics.
    """
    filled = {}

    # ── Company / Firma ──────────────────────────────────────
    filled["company"] = await _fill_field(page, [
        "input[name*='firma' i]",
        "input[name*='company' i]",
        "input[name*='unternehmen' i]",
        "input[placeholder*='Firma' i]",
        "input[placeholder*='Unternehmen' i]",
        "input[placeholder*='Company' i]",
        "input[placeholder*='Firmenname' i]",
        "[aria-label*='Firma' i]",
        "[aria-label*='Unternehmen' i]",
    ], TEST_DATA["company"])

    # ── Name ─────────────────────────────────────────────────
    filled["name"] = await _fill_field(page, [
        "input[name='name' i]",
        "input[name*='fullname' i]",
        "input[name*='full_name' i]",
        "input[placeholder*='Vor- und Nachname' i]",
        "input[placeholder*='Name' i]",
        "input[placeholder*='Ihr Name' i]",
        "[aria-label*='Name' i]",
    ], TEST_DATA["name"])

    if not filled["name"]:
        await _fill_field(page, [
            "input[name*='vorname' i]",
            "input[name*='firstname' i]",
            "input[placeholder*='Vorname' i]",
        ], "Test")
        await _fill_field(page, [
            "input[name*='nachname' i]",
            "input[name*='lastname' i]",
            "input[placeholder*='Nachname' i]",
        ], "User")

    # ── Email ─────────────────────────────────────────────────
    filled["email"] = await _fill_field(page, [
        "input[type='email']",
        "input[name*='email' i]",
        "input[name*='mail' i]",
        "input[placeholder*='E-Mail' i]",
        "input[placeholder*='Email' i]",
        "input[placeholder*='Ihre E-Mail' i]",
        "input[placeholder*='E-Mail-Adresse' i]",
        "[aria-label*='E-Mail' i]",
        "[aria-label*='Email' i]",
    ], TEST_DATA["email"])

    # ── Phone ─────────────────────────────────────────────────
    filled["phone"] = await _fill_field(page, [
        "input[type='tel']",
        "input[name*='phone' i]",
        "input[name*='telefon' i]",
        "input[name*='tel' i]",
        "input[placeholder*='Telefon' i]",
        "input[placeholder*='Phone' i]",
        "input[placeholder*='Tel' i]",
        "input[placeholder*='Ihre Telefonnummer' i]",
        "[aria-label*='Telefon' i]",
    ], TEST_DATA["phone"])

    # ── Message / Nachricht ───────────────────────────────────
    filled["message"] = await _fill_field(page, [
        "textarea[name*='message' i]",
        "textarea[name*='nachricht' i]",
        "textarea[name*='mitteilung' i]",
        "textarea[name*='msg' i]",
        "textarea[name*='anfrage' i]",
        "textarea[name*='kommentar' i]",
        "textarea[placeholder*='Nachricht' i]",
        "textarea[placeholder*='Message' i]",
        "textarea[placeholder*='Ihre Nachricht' i]",
        "textarea[placeholder*='Anfrage' i]",
        "textarea[placeholder*='Kommentar' i]",
        "textarea",  # last resort: any textarea
    ], message)

    return filled


async def _submit_form(page: Page) -> bool:
    """
    Click the submit button. Returns True if a button was found and clicked.
    """
    submit_re = re.compile(
        r"senden|absenden|submit|anfrage senden|nachricht senden|jetzt senden"
        r"|angebot anfordern|kostenloses angebot|anfragen|abschicken|bestätigen",
        re.IGNORECASE,
    )

    btn = None
    for selector in ["button[type='submit']", "input[type='submit']"]:
        try:
            el = page.locator(selector).first
            if await el.is_visible(timeout=SHORT_TIMEOUT):
                btn = el
                break
        except Exception:
            continue

    if btn is None:
        try:
            candidate = page.get_by_role("button", name=submit_re).first
            if await candidate.is_visible(timeout=SHORT_TIMEOUT):
                btn = candidate
        except Exception:
            pass

    if btn is None:
        return False

    # Wait for Turnstile/CAPTCHA to resolve
    try:
        await btn.wait_for(state="enabled", timeout=8_000)
    except Exception:
        print("  [WARN] Submit button may still be blocked by CAPTCHA")

    try:
        await btn.click()
        await page.wait_for_timeout(2_000)
        return True
    except Exception:
        return False


async def _detect_success(page: Page, had_form_before_submit: bool) -> bool:
    """
    Check for a success signal after form submission.
    Uses multiple strategies to detect thank-you messages.
    """
    await page.wait_for_timeout(6_000)  # wait longer for async responses

    # Strategy 1 — look for explicit post-submit confirmation text.
    # Keep this narrow; broad static marketing copy can create false passes.
    success_re = re.compile(
        r"vielen\s+dank|danke\s+(?:f[uü]r|for)|thank\s+you"
        r"|(?:nachricht|anfrage|formular).{0,40}(?:gesendet|eingegangen|erfolgreich|erhalten)"
        r"|(?:message|request|form).{0,40}(?:sent|submitted|received|successful)"
        r"|wir\s+melden\s+uns|we.?ll\s+be\s+in\s+touch|in\s+k[uü]rze",
        re.IGNORECASE,
    )
    try:
        msg = page.get_by_text(success_re).first
        if await msg.is_visible(timeout=3_000):
            print(f"  [INFO] Success message detected on page")
            return True
    except Exception:
        pass

    # Strategy 2 — check URL for confirmation keywords
    current_url = page.url.lower()
    success_urls = ["danke", "thank", "success", "confirm", "bestaetigung",
                    "bestätigung", "submitted", "gesendet"]
    if any(kw in current_url for kw in success_urls):
        print(f"  [INFO] Success detected via URL: {current_url}")
        return True

    # Strategy 3 — check for hidden/shown success div
    try:
        success_div = page.locator(
            ".success, .alert-success, .form-success, "
            ".w-form-done, [class*='w-form-done'], "
            "[class*='success'], [class*='danke'], "
            "[id*='success'], [id*='danke'], "
            ".wpcf7-response-output, .contact-success"
        ).first
        count = await success_div.count()
        if count > 0 and await success_div.is_visible(timeout=2_000):
            print(f"  [INFO] Success div detected")
            return True
    except Exception:
        pass

    # Strategy 4 — form disappeared (replaced by success message)
    try:
        form_count = await page.locator("form").count()
        if had_form_before_submit and form_count == 0:
            print(f"  [INFO] Form disappeared — likely submitted successfully")
            return True
    except Exception:
        pass

    return False


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

async def submit_form(page: Page, domain: str, run_id: str) -> dict:
    """
    Navigate to the contact section, fill the form, and submit.
    Logs detailed results for each QA requirement.
    """
    base_url = _base_url_from_domain(domain)
    message  = f"QA Test - run_id={run_id}"

    print(f"  ┌─────────────────────────────────────────")
    print(f"  │ CONTACT FORM QA CHECKS — {domain}")
    print(f"  ├─────────────────────────────────────────")

    try:
        # ── CHECK 1: Contact form exists? ─────────────────────
        reached = await _navigate_to_contact(page, base_url)
        if not reached:
            print(f"  │ [1] Contact form exists     : ❌ NOT FOUND")
            print(f"  │ [2] Input fields functional : ⏭  SKIPPED")
            print(f"  │ [3] Submit button present   : ⏭  SKIPPED")
            print(f"  │ [4] Auto-fill test data     : ⏭  SKIPPED")
            print(f"  │ [5] Submit button clicked   : ⏭  SKIPPED")
            print(f"  └─────────────────────────────────────────")
            return {"status": "FAIL", "error": "Could not find contact section"}

        print(f"  │ [1] Contact form exists     : ✅ FOUND at {page.url}")

        # Switch to Serviceanfrage tab if present
        await _switch_to_serviceanfrage(page)

        # ── CHECK 2: Input fields functional? ─────────────────
        filled = await _fill_form(page, message)
        filled_fields   = [f for f, ok in filled.items() if ok]
        unfilled_fields = [f for f, ok in filled.items() if not ok]

        if filled_fields:
            print(f"  │ [2] Input fields functional : ✅ Filled: {filled_fields}")
        else:
            print(f"  │ [2] Input fields functional : ❌ No fields could be filled")

        if unfilled_fields:
            print(f"  │     Fields not found        : ⚠️  {unfilled_fields}")

        # ── CHECK 4: Auto-fill with test data ─────────────────
        if filled_fields:
            print(f"  │ [4] Auto-fill test data     : ✅ Test data injected")
            print(f"  │     Name={TEST_DATA['name']} | Email={TEST_DATA['email']} | Phone={TEST_DATA['phone']}")
        else:
            print(f"  │ [4] Auto-fill test data     : ❌ Could not inject test data")

        # Require at minimum: email OR message to be filled
        if not filled.get("email") and not filled.get("message"):
            print(f"  │ [3] Submit button present   : ⏭  SKIPPED (no fields filled)")
            print(f"  │ [5] Submit button clicked   : ⏭  SKIPPED")
            print(f"  └─────────────────────────────────────────")
            return {
                "status": "FAIL",
                "error":  f"Could not fill required fields: {unfilled_fields}",
            }

        # ── CHECK 3: Submit button present? ───────────────────
        form_count_before_submit = await page.locator("form").count()

        # Check if submit button exists before clicking
        btn_exists = False
        for selector in ["button[type='submit']", "input[type='submit']"]:
            try:
                el = page.locator(selector).first
                if await el.count() > 0:
                    btn_exists = True
                    break
            except Exception:
                pass

        if not btn_exists:
            # Try text-based button
            try:
                import re as _re
                submit_re = _re.compile(
                    r"senden|absenden|submit|anfrage|abschicken|bestätigen",
                    _re.IGNORECASE,
                )
                candidate = page.get_by_role("button", name=submit_re).first
                if await candidate.count() > 0:
                    btn_exists = True
            except Exception:
                pass

        if btn_exists:
            print(f"  │ [3] Submit button present   : ✅ FOUND")
        else:
            print(f"  │ [3] Submit button present   : ⚠️  Not found via standard selectors")

        # ── CHECK 5: Submit button clicked? ───────────────────
        submitted = await _submit_form(page)
        if submitted:
            print(f"  │ [5] Submit button clicked   : ✅ CLICKED")
        else:
            print(f"  │ [5] Submit button clicked   : ❌ FAILED — button not clickable")
            print(f"  └─────────────────────────────────────────")
            return {"status": "FAIL", "error": "Submit button not found or not clickable"}

        # ── Success detection ──────────────────────────────────
        success = await _detect_success(page, form_count_before_submit > 0)
        if success:
            print(f"  │     Success confirmation    : ✅ Detected on page")
        else:
            print(f"  │     Success confirmation    : ⚠️  Not detected (CAPTCHA may have blocked)")

        print(f"  └─────────────────────────────────────────")

        if success:
            return {"status": "PASS", "error": ""}
        else:
            return {"status": "FAIL", "error": "No success confirmation detected after submit"}

    except PlaywrightTimeoutError as e:
        print(f"  │ ❌ TIMEOUT ERROR: {e}")
        print(f"  └─────────────────────────────────────────")
        return {"status": "FAIL", "error": f"Timeout: {e}"}

    except Exception as e:
        print(f"  │ ❌ EXCEPTION: {e}")
        print(f"  └─────────────────────────────────────────")
        return {"status": "FAIL", "error": str(e)}