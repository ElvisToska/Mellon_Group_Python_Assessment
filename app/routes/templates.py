import logging
import sys

from datetime import datetime
from urllib import response

from flask import Flask, jsonify, request, Blueprint
from sqlalchemy import text
from sqlalchemy.ext.asyncio import result

from db.cache import cache_clear_all, cache_get, cache_set, redis_client
from db.db_connection import engine
from db.schema_utils import ensure_updated_on_column, ensure_decommission_queue_table


logger = logging.getLogger(__name__)

templates_bp = Blueprint("templates", __name__)


# --- get all templates ----------------------------------------------------------------
@templates_bp.route("/templates", methods=["GET"])
def list_templates():
    """
    Gets all of the templates in the database
    it retrieves the id, template_name, hardware_model, and hardware_family for each template
    :return: JSON list of templates
    """
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT id, template_name, hardware_model, hardware_family
                    FROM templates
                """)
            ).mappings().all()
            logger.info(f"Got {len(rows)} templates from the database")

            # Convert the rows to a list of dictionaries
            result = []
            for row in rows:
                result.append({
                    "id": row["id"],
                    "template_name": row["template_name"],
                    "hardware_model": row["hardware_model"],
                    "hardware_family": row["hardware_family"]
                })
            logger.info(f"Returning {len(result)} templates as JSON")

            return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error fetching templates: {e}")
        return jsonify({"error": "database error"}), 500


# --- get a specific template by ID ------------------------------------------------------
@templates_bp.route("/templates/<int:id>", methods=["GET"])
def get_template(id):
    """
    Get a specific template by ID
    it retrieves the id, template_name, hardware_model, and hardware_family for the template
    :param id: The ID of the template
    :return: JSON representation of the template
    """
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT id, template_name, hardware_model, hardware_family
                    FROM templates
                    WHERE id = :id
                """),
                {"id": id}
            ).mappings().first()

            # check if the template exists
            if row is None:
                logger.error(f"Template with ID {id} not found")
                return jsonify({"error": "template not found"}), 404
            logger.info(f"Got template with ID {id} from the database")

            # Convert the row to a dictionary
            result = {
                "id": row["id"],
                "template_name": row["template_name"],
                "hardware_model": row["hardware_model"],
                "hardware_family": row["hardware_family"]
            }
            logger.info(f"Returning template with ID {id} as JSON")

            return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error fetching template with ID {id}: {e}")
        return jsonify({"error": "database error"}), 500



