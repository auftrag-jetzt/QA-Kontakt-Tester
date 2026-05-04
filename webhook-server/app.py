"""
Webhook server for Airtable QA automation.
Listens for POST requests from Airtable and runs the QA pipeline.
"""

import sys
import os
import json
import logging
from flask import Flask, request, jsonify

# Add parent directory to path so we can import visual_qa
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from visual_qa import run_domain, set_status_to_testing, write_qa_result_to_airtable

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.route('/run-qa', methods=['POST'])
def run_qa():
    """
    Webhook endpoint for Airtable automation.

    Expects JSON body:
    {
       record_id = data.get('record_id')
domain = data.get('domain', '')

# Strip https:// or http:// prefix if present
if domain.startswith('https://'):
    domain = domain[8:]
elif domain.startswith('http://'):
    domain = domain[7:]
# Remove trailing slash
domain = domain.rstrip('/')
    }

    Two-stage write-back (prevents duplicate triggers):
    1. Immediately set Airtable status → "testing"
    2. Run QA pipeline
    3. Set final status → "passed" or "failed"

    Returns:
    {
        "status": "PASS" | "PARTIAL" | "FAIL",
        "message": "QA run completed",
        "airtable_status": "passed" | "failed"
    }
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "No JSON body provided"}), 400

        record_id = data.get('record_id')
        domain = data.get('domain')

        # Validate inputs
        if not domain:
            return jsonify({"error": "Missing 'domain' field"}), 400

        logger.info(f"Starting QA run for domain: {domain}, record_id: {record_id}")

        # STAGE 1: Immediately lock the record by setting status to "testing"
        # This prevents Airtable automation from triggering again
        if record_id:
            logger.info(f"Locking record: setting status to 'testing'")
            set_status_to_testing(record_id)
        else:
            logger.warning("No record_id provided, skipping Airtable lock")

        # STAGE 2: Run the QA pipeline
        try:
            result = run_domain(domain, airtable_record_id=record_id)
        except Exception as pipeline_error:
            logger.error(f"Pipeline error: {str(pipeline_error)}")
            error_msg = str(pipeline_error)
            if record_id:
                write_qa_result_to_airtable(record_id, "FAIL", error_msg=error_msg)
            return jsonify({
                "error": error_msg,
                "status": "FAIL"
            }), 500

        # STAGE 3: Write final result back to Airtable
        # Note: write_qa_result_to_airtable is called inside run_domain()
        # when airtable_record_id is provided, but we also call it here
        # to ensure error details are captured
        if record_id:
            final_status = result.get('status', 'FAIL')
            error_msg = result.get('error', '')
            logger.info(f"Writing final status '{final_status}' to Airtable")
            write_qa_result_to_airtable(record_id, final_status, error_msg=error_msg)

        logger.info(f"QA run completed. Status: {result.get('status')}")

        return jsonify({
            "status": result.get('status'),
            "message": "QA run completed",
            "airtable_record_id": record_id,
            "details": {
                "domain": result.get('domain'),
                "gemini_status": result.get('gemini_status'),
                "form_status": result.get('form_status'),
                "airtable_verified": result.get('airtable_verified'),
            }
        }), 200

    except Exception as e:
        logger.error(f"Error in webhook: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"}), 200


@app.route('/', methods=['GET'])
def index():
    """Root endpoint with API documentation."""
    return jsonify({
        "service": "Airtable QA Webhook",
        "version": "1.0",
        "endpoints": {
            "POST /run-qa": "Run QA pipeline for a domain",
            "GET /health": "Health check",
            "GET /": "This message"
        }
    }), 200


if __name__ == '__main__':
    # For development: app.run(debug=True, host='0.0.0.0', port=5000)
    # For production (Coolify): use gunicorn or similar
    app.run(debug=False, host='0.0.0.0', port=5000)
