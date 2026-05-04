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

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError


# ─────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────

# Test data injected into every form
TEST_DATA = {
    "company": "QA Automation",
    "name":    "Test User",
    "email":   "qa@test.com",
    "phone":   "+491234567890",
}

# Timeouts
SHORT_TIMEOUT = 3_000   # ms — for optional elements (tabs, selectors)
FILL_TIMEOUT  = 2_000   # ms — for individual field visibility check

# Keywords to identify the contact link in navigation
_CONTACT_RE = re.compile(r"kontakt|contact|anfrage", re.IGNORECASE)

# Keywords for the Serviceanfrage tab
_SERVICE_RE = re.compile(r"serviceanfrage|anfrage|service request", re.IGNORECASE)

# Common URL paths to try if nav click fails
_CONTACT_PATHS = ["/kontakt", "/kontakt/", "/contact", "/contact/"]


# ─────────────────────────────────────────────────────────────
# Internal Helpers
# ─────────────────────────────────────────────────────────────

async def _navigate_to_contact(page: Page, base_url: str) -> bool:
    """
    Attempt to reach the contact section via three strategies:
      1. Click a navigation link containing contact keywords
      2. Navigate directly to known contact URL paths
      3. Scroll to an in-page #kontakt / #contact anchor
    Returns True if any strategy succeeded.
    """
    # Strategy 1 — click nav link
    try:
        link = page.get_by_role("link", name=_CONTACT_RE).first
        if await link.is_visible(timeout=SHORT_TIMEOUT):
            await link.click()
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(1_000)
            return True
    except Exception:
        pass

    # Strategy 2 — direct URL navigation
    for path in _CONTACT_PATHS:
        try:
            response = await page.goto(
                base_url + path,
                wait_until="domcontentloaded",
                timeout=10_000,
            )
            if response and response.status < 400:
                await page.wait_for_timeout(1_000)
                return True
        except Exception:
            continue

    # Strategy 3 — in-page anchor scroll
    try:
        section = page.locator("#kontakt, #contact, [id*='kontakt'], [id*='contact']").first
        if await section.count() > 0:
            await section.scroll_into_view_if_needed()
            await page.wait_for_timeout(500)
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
        # Try tab role first, then fall back to any clickable text match
        tab = page.get_by_role("tab", name=_SERVICE_RE).first
        if not await tab.is_visible(timeout=SHORT_TIMEOUT):
            tab = page.get_by_role("button", name=_SERVICE_RE).first
        if not await tab.is_visible(timeout=SHORT_TIMEOUT):
            tab = page.get_by_text(_SERVICE_RE).first

        if await tab.is_visible(timeout=SHORT_TIMEOUT):
            await tab.click()
            await page.wait_for_timeout(1_000)
    except Exception:
        pass  # Tab not present — continue with visible form


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
        "[aria-label*='Firma' i]",
        "[aria-label*='Unternehmen' i]",
    ], TEST_DATA["company"])

    # ── Name ─────────────────────────────────────────────────
    # Try full-name field first, then first/last separately
    filled["name"] = await _fill_field(page, [
        "input[name='name' i]",
        "input[name*='fullname' i]",
        "input[name*='full_name' i]",
        "input[placeholder*='Vor- und Nachname' i]",
        "input[placeholder*='Name' i]",
        "[aria-label*='Name' i]",
    ], TEST_DATA["name"])

    if not filled["name"]:
        # Split name into first / last for two-field forms
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
        "[aria-label*='E-Mail' i]",
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
        "[aria-label*='Telefon' i]",
    ], TEST_DATA["phone"])

    # ── Message / Nachricht ───────────────────────────────────
    filled["message"] = await _fill_field(page, [
        "textarea[name*='message' i]",
        "textarea[name*='nachricht' i]",
        "textarea[name*='mitteilung' i]",
        "textarea[name*='msg' i]",
        "textarea[placeholder*='Nachricht' i]",
        "textarea[placeholder*='Message' i]",
        "textarea[placeholder*='Ihre Nachricht' i]",
        "textarea",  # last resort: any textarea
    ], message)

    return filled


async def _submit_form(page: Page) -> bool:
    """
    Click the submit button. Returns True if a button was found and clicked.
    Includes a Turnstile bypass check — waits for the button to become
    enabled after stealth scripts have loaded.
    """
    submit_re = re.compile(
        r"senden|absenden|submit|anfrage senden|nachricht senden|jetzt senden",
        re.IGNORECASE,
    )

    # Locate the submit button (prefer type=submit, fall back to text match)
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
        # Fall back to text-matching button
        try:
            candidate = page.get_by_role("button", name=submit_re).first
            if await candidate.is_visible(timeout=SHORT_TIMEOUT):
                btn = candidate
        except Exception:
            pass

    if btn is None:
        return False

    # -- Turnstile bypass check ------------------------------------------
    # After stealth scripts run, Turnstile may take a moment to resolve.
    # Wait up to 8s for the button to become enabled before clicking.
    TURNSTILE_WAIT_MS = 8_000
    try:
        await btn.wait_for(state="enabled", timeout=TURNSTILE_WAIT_MS)
    except Exception:
        print("  [WARN] Turnstile still blocking submission")
        # Attempt click anyway — stealth may have partially bypassed it

    try:
        await btn.click()
        await page.wait_for_timeout(1_500)  # wait for CF async validation
        return True
    except Exception:
        return False


async def _detect_success(page: Page) -> bool:
    """
    Check for a success signal after form submission:
      - URL change (redirect to confirmation page)
      - Visible success message text
    """
    await page.wait_for_timeout(2_000)  # wait for response

    # Check for common success message patterns
    success_re = re.compile(
        r"danke|vielen dank|thank you|erfolgreich|success|gesendet|sent|wird bearbeitet",
        re.IGNORECASE,
    )
    try:
        msg = page.get_by_text(success_re).first
        if await msg.is_visible(timeout=3_000):
            return True
    except Exception:
        pass

    # Check if URL changed to a confirmation path
    current_url = page.url.lower()
    if any(kw in current_url for kw in ["danke", "thank", "success", "confirm", "bestaetigung"]):
        return True

    return False


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

async def submit_form(page: Page, domain: str, run_id: str) -> dict:
    """
    Navigate to the contact section, fill the form, and submit.

    Args:
        page    : Active Playwright page (already on the domain's homepage).
        domain  : Domain string e.g. "example.de" (used for URL construction).
        run_id  : Unique run identifier embedded in the message field.

    Returns:
        dict: {
            "status": "PASS" | "FAIL",
            "error":  str   (empty string on success)
        }
    """
    base_url = f"https://{domain}"
    message  = f"run_id={run_id}"

    try:
        # Step 1 — Navigate to contact section
        reached = await _navigate_to_contact(page, base_url)
        if not reached:
            return {"status": "FAIL", "error": "Could not find contact section"}

        # Step 2 — Switch to Serviceanfrage tab if present
        await _switch_to_serviceanfrage(page)

        # Step 3 — Fill the form
        filled = await _fill_form(page, message)

        # Require at minimum: email + message to be filled
        if not filled.get("email") or not filled.get("message"):
            missing = [f for f, ok in filled.items() if not ok]
            return {
                "status": "FAIL",
                "error":  f"Could not fill required fields: {missing}",
            }

        # Step 4 — Submit
        submitted = await _submit_form(page)
        if not submitted:
            return {"status": "FAIL", "error": "Submit button not found"}

        # Step 5 — Detect success
        success = await _detect_success(page)
        if success:
            return {"status": "PASS", "error": ""}
        else:
            return {"status": "FAIL", "error": "No success confirmation detected after submit"}

    except PlaywrightTimeoutError as e:
        return {"status": "FAIL", "error": f"Timeout: {e}"}

    except Exception as e:
        return {"status": "FAIL", "error": str(e)}
