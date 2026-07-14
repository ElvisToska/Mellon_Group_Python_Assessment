import csv
import io
import logging

from flask import Blueprint, Response, jsonify
from sqlalchemy import text

from db.db_connection import engine

logger = logging.getLogger(__name__)

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/reports/terminals_basic.csv", methods=["GET"])
def terminals_basic_csv():
    """
    Generate a CSV file containing basic information about terminals.
    :return: Flask Response object containing the CSV file
    """

    try:
        with engine.connect() as conn:

            rows = conn.execute(
                text("""
                    SELECT t.tid, m.mid, t.hardware_model, t.software_version,
                        t.enabled, t.last_call_stamp
                    FROM terminals t
                    JOIN merchants m ON t.merchant_id = m.id
                    ORDER BY t.tid
                """)
            ).mappings().all()

    except Exception as e:
        logger.error(f"Error creating terminals_basic.csv: {e}")
        return jsonify({"error": "database error"}), 500

    # Create an empty CSV file in memory
    csv_file = io.StringIO()

    # Create a CSV writer
    writer = csv.writer(csv_file)

    # Write the first row with the column names
    writer.writerow([
        "tid",
        "mid",
        "hardware_model",
        "software_version",
        "enabled",
        "last_call"
    ])

    # Write row in CSV for every terminal
    for row in rows:

        last_call = row["last_call_stamp"]

        if last_call is not None:
            last_call = last_call.strftime("%Y-%m-%dT%H:%M:%S")

        enabled = row["enabled"]
        if enabled == 1:
            enabled = "true"
        else:
            enabled = "false"

        writer.writerow([
            row["tid"],
            row["mid"],
            row["hardware_model"],
            row["software_version"],
            enabled,
            last_call
        ])

    # Return the CSV file as the response
    return Response(
        csv_file.getvalue(),
        content_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=terminals_basic.csv"
        }
    )