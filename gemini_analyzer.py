"""
gemini_analyzer.py — Gemini Visual QA Analysis Module
======================================================

Sends a website screenshot to Gemini (gemini-1.5-flash) and returns
a structured QA result dictionary.

Installation:
    pip install google-generativeai

Usage:
    from gemini_analyzer import analyze_screenshot

    result = analyze_screenshot("screenshots/example.com.png")
    # {"status": "PASS" or "FAIL", "issues": [...]}
"""

import json
import os
import re
import warnings

# Suppress deprecation warning from the google-generativeai package
# (switch to google.genai when GEMINI_API_KEY is integrated)
with warnings.catch_warnings():
    warnings.simplefilter("ignore", FutureWarning)
    import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from PIL import Image


# ─────────────────────────────────────────────────────────────
# Gemini Setup  (runs once at import time)
# ─────────────────────────────────────────────────────────────

_api_key = os.environ.get("GEMINI_API_KEY")
if not _api_key:
    raise EnvironmentError(
        "GEMINI_API_KEY environment variable is not set.\n"
        "Set it with: set GEMINI_API_KEY=your_key_here"
    )

genai.configure(api_key=_api_key)

_MODEL = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    generation_config=GenerationConfig(
        temperature=0.1,       # low temp → deterministic, structured output
        max_output_tokens=512,
    ),
)


# ─────────────────────────────────────────────────────────────
# QA Prompt
# ─────────────────────────────────────────────────────────────

QA_PROMPT = """You are a QA expert.
Analyze this website screenshot for:
- overlapping elements
- text cut off
- layout issues
- misalignment

Return ONLY valid JSON with no markdown, no explanation, no code block:
{
  "status": "PASS" or "FAIL",
  "issues": ["issue1", "issue2"]
}

If there are no issues, return:
{"status": "PASS", "issues": []}"""


# ─────────────────────────────────────────────────────────────
# JSON Parser (safe)
# ─────────────────────────────────────────────────────────────

def _parse_gemini_response(raw_text: str) -> dict:
    """
    Safely extract JSON from Gemini's response.
    Handles:
      - Clean JSON
      - JSON wrapped in markdown ```json ... ```
      - Partial/malformed responses
    """
    # 1. Try direct parse first
    try:
        return json.loads(raw_text.strip())
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown code fences and retry
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw_text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 3. Extract the first JSON object via regex
    match = re.search(r"\{.*?\}", raw_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # 4. Fallback: couldn't parse, mark as error
    return {
        "status": "FAIL",
        "issues": [f"Could not parse Gemini response: {raw_text[:200]}"],
    }


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

def analyze_screenshot(image_path: str) -> dict:
    """
    Analyze a website screenshot using Gemini Vision.

    Args:
        image_path (str): Absolute or relative path to a .png/.jpg screenshot.

    Returns:
        dict: {
            "status": "PASS" | "FAIL",
            "issues": list[str]
        }

    Raises:
        FileNotFoundError: If image_path does not exist.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Screenshot not found: {image_path}")

    try:
        image = Image.open(image_path)
        response = _MODEL.generate_content([QA_PROMPT, image])
        result = _parse_gemini_response(response.text)

        # Validate and normalize structure
        return {
            "status": str(result.get("status", "FAIL")).upper(),
            "issues": list(result.get("issues", [])),
        }

    except Exception as exc:
        return {
            "status": "FAIL",
            "issues": [f"Gemini API error: {str(exc)}"],
        }


# ─────────────────────────────────────────────────────────────
# Quick Test (run directly)
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python gemini_analyzer.py <path_to_screenshot.png>")
        sys.exit(1)

    path = sys.argv[1]
    print(f"Analyzing: {path}")

    result = analyze_screenshot(path)

    print(f"\nStatus : {result['status']}")
    if result["issues"]:
        print("Issues :")
        for issue in result["issues"]:
            print(f"  • {issue}")
    else:
        print("Issues : None")
