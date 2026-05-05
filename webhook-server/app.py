"""
Webhook server for Airtable QA automation.
Runs QA pipeline in background thread so webhook returns immediately.
"""

import sys
import os
import logging
import threading
from flask import Flask, request, jsonify

sys.path.insert(0, os.path.dirname(__file__))

from visual_qa import run_domain, set_status_to_testing, write_qa_result_to_airtable

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_qa_background(domain, record_id):
    """Run the full QA pipeline in a background thread."""
    try:
        logger.info(f"[BG] Starting QA for {domain} / {record_id}")
        result = run_domain(domain)
        final_status = result.get('status', 'FAIL')
        error_msg = (
            result.get('error', '')
            or result.get('form_error', '')
            or result.get('airtable_error', '')
        )
        if final_status == "PASS":
            error_msg = ""
        logger.info(
            "[BG] QA done: %s | Gemini=%s Form=%s API=%s Verified=%s Error=%s",
            final_status,
            result.get('gemini_status'),
            result.get('form_status'),
            result.get('api_submission'),
            result.get('airtable_verified'),
            error_msg or "",
        )
        write_qa_result_to_airtable(record_id, final_status, error_msg=error_msg)
    except Exception as e:
        logger.error(f"[BG] Pipeline error: {e}", exc_info=True)
        try:
            write_qa_result_to_airtable(record_id, "FAIL", error_msg=str(e)[:500])
        except Exception:
            pass


@app.route('/run-qa', methods=['POST'])
def run_qa():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON body"}), 400

        record_id = data.get('record_id')
        domain = data.get('domain', '')

        # Strip URL prefix
        if domain.startswith('https://'):
            domain = domain[8:]
        elif domain.startswith('http://'):
            domain = domain[7:]
        domain = domain.rstrip('/')

        if not domain:
            return jsonify({"error": "Missing domain"}), 400

        logger.info(f"Received QA request: {domain} / {record_id}")

        # Lock record immediately
        if record_id:
            set_status_to_testing(record_id)

        # Run pipeline in background — return immediately to Airtable
        thread = threading.Thread(
            target=run_qa_background,
            args=(domain, record_id),
            daemon=True
        )
        thread.start()

        return jsonify({
            "status": "started",
            "message": "QA pipeline started in background",
            "domain": domain,
            "record_id": record_id
        }), 200

    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"}), 200


@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "service": "Airtable QA Webhook",
        "endpoints": {"POST /run-qa": "Start QA", "GET /health": "Health check"}
    }), 200


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)
