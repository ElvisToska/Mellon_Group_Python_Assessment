import logging

from flask import Flask, jsonify, request, Blueprint
from sqlalchemy import text
from sqlalchemy.ext.asyncio import result

from db.cache import cache_clear_all, cache_get, cache_set, redis_client
from db.db_connection import engine
from db.schema_utils import ensure_updated_on_column, ensure_decommission_queue_table

logger = logging.getLogger(__name__)

health_bp = Blueprint("health", __name__)


# --- Health check ------------------------------------------------------
@health_bp.route('/health')
def health():
    """
    Health check endpoint to verify the status of the database and cache.
    :return: JSON response containing the status of the database and cache
    """
    status = {"status": "ok", "database": "unknown", "cache": "unknown"}

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        status["database"] = "ok"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        status["database"] = f"error: {e}"
        status["status"] = "degraded"

    try:
        redis_client.ping()
        status["cache"] = "ok"
    except Exception as e:
        logger.error(f"Cache health check failed: {e}")
        status["cache"] = f"error: {e}"
        status["status"] = "degraded"

    code = 200 if status["status"] == "ok" else 503
    return jsonify(status), code