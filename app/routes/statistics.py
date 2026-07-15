import logging
from datetime import datetime

from flask import jsonify, Blueprint
from sqlalchemy import text

from db.cache import cache_get, cache_set
from db.db_connection import engine

import pandas as pd


logger = logging.getLogger(__name__)

statistics_bp = Blueprint("statistics", __name__)


# --- statistics based on hardware model ----------------------------------------
@statistics_bp.route("/statistics/by-hardware", methods=["GET"])
def statistics_by_hardware():
    """
    This endpoint returns statistics based on the hardware model of the terminals.
    It retrieves the hardware model from the database, groups the terminals by hardware model,
    and counts the number of terminals for each hardware model.
    The result is cached for 30 seconds to improve performance.
    :return: A JSON response containing the generated timestamp and a list of dictionaries with hardware model and count.
    """

    # Check cache first
    cache_key = "statistics:by-hardware"
    cached = cache_get(cache_key)
    if cached is not None:
        return jsonify(cached)


    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(""
                     "SELECT hardware_model " # getting only the hardware_model column
                     "FROM terminals"))
            rows = result.fetchall()
            logger.info(f"Fetched {len(rows)} rows from the database for hardware model statistics.")
            df = pd.DataFrame(rows, columns=result.keys())

        # Group by hardware_model and count
        stats = df.groupby('hardware_model').size().reset_index(name='count')
        logger.info(f"Generated hardware model statistics for {len(stats)} hardware models.")

        # From list to dictionaries
        data = stats.to_dict(orient='records')

        response = {
            #adding the timestamp of the generation
            "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "data": data
        }

        # Cache the result for 30 seconds
        cache_set(cache_key, response, ttl=60)

        return jsonify(response)

    except Exception as e:
        logger.error(f"Error generating statistics by hardware: {e}")
        return jsonify({"error": "database error"}), 500



# --- statistics based on state (active/inactive) ----------------------------------------
@statistics_bp.route("/statistics/by-state", methods=["GET"])
def statistics_by_state():
    """
    This endpoint returns statistics based on the state of the terminals (active/inactive).
    It retrieves the enabled status from the database, groups the terminals by their enabled status,
    and counts the number of terminals for each state. The result is cached for 30 seconds to improve performance.
    :return: A JSON response containing the generated timestamp, counts of active, inactive, and total terminals.
    """

    # Check cache first
    cache_key = "statistics:by-state"
    cached = cache_get(cache_key)
    if cached is not None:
        return jsonify(cached)

    # Active vs Inactive devices and total count
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(""
                     "SELECT enabled " # getting only the enabled column
                     "FROM terminals"))
            rows = result.fetchall()
            logger.info(f"Fetched {len(rows)} rows from the database for state statistics.")
            df = pd.DataFrame(rows, columns=result.keys())

        # Count active and inactive terminals with pandas
        state_counts = df["enabled"].value_counts()
        active = int(state_counts.get(1, 0))
        inactive = int(state_counts.get(0, 0))

        response = {
            "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            # adding the counts of active, inactive and total devices
            "active": active,
            "inactive": inactive,
            "total": active + inactive
        }

        # Cache the result for 30 seconds
        cache_set(cache_key, response, ttl=60)

        return jsonify(response)

    except Exception as e:
        logger.error(f"Error generating statistics by state: {e}")
        return jsonify({"error": "database error"}), 500



# --- statistics based on hardware family ----------------------------------------
@statistics_bp.route("/statistics/by-hardware-family", methods=["GET"])
def statistics_by_hardware_family():
    """
    This endpoint returns statistics based on the hardware family of the terminals.
    It retrieves the hardware family from the database, groups the terminals by hardware family,
    and counts the number of terminals for each hardware family. The result is cached for 30 seconds to improve performance.
    :return: A JSON response containing the generated timestamp and a list of dictionaries with hardware family and count.
    """

    # Check cache first
    cache_key = "statistics:by-hardware-family"
    cached = cache_get(cache_key)
    if cached is not None:
        return jsonify(cached)

    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(""
                     "SELECT hardware_family " # getting only the hardware_family column
                     "FROM terminals"))
            rows = result.fetchall()
            logger.info(f"Fetched {len(rows)} rows from the database for hardware family statistics.")
            df = pd.DataFrame(rows, columns=result.keys())

        # Group by hardware_family and count
        stats = df.groupby('hardware_family').size().reset_index(name='count')
        logger.info(f"Generated hardware family statistics for {len(stats)} hardware families.")

        response = {
            "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "data": stats.to_dict(orient='records')
        }

        # Cache the result for 30 seconds
        cache_set(cache_key, response, ttl=60)

        return jsonify(response)

    except Exception as e:
        logger.error(f"Error generating statistics by hardware family: {e}")
        return jsonify({"error": "database error"}), 500


# --- statistics based on idle distribution ----------------------------------------
@statistics_bp.route("/statistics/idle-distribution", methods=["GET"])
def statistics_idle_distribution():
    """
    This endpoint returns statistics based on the idle distribution of the terminals.
    It retrieves the last_call_stamp from the database, calculates the number of days since the last
    call for each terminal, and groups the terminals into predefined buckets based on the number of days since the last call.
    The result is cached for 30 seconds to improve performance.
    :return: A JSON response containing the generated timestamp and a list of dictionaries with idle distribution statistics.
    """

    # Check cache first
    cache_key = "statistics:idle-distribution"
    cached = cache_get(cache_key)
    if cached is not None:
        return jsonify(cached)


    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(""
                     "SELECT last_call_stamp "
                     "FROM terminals"))
            rows = result.fetchall()
            logger.info(f"Fetched {len(rows)} rows from the database for idle distribution statistics.")
            df = pd.DataFrame(rows, columns=result.keys())

        # Calculate days since last_call_stamp
        df['days_since_last_call'] = (datetime.now() - pd.to_datetime(df['last_call_stamp'])).dt.days

        # Define buckets of days since last call : today, 1-7 days, 8-30 days, 31-90 days, 90+ days
        bins = [-1, 0, 7, 30, 90, float('inf')] # -1 to include today (0 days)
        labels = ['Σήμερα', '1-7 μέρες', '8-30 μέρες', '31-90 μέρες', '90+ μέρες']
        # Create a new column 'range'
        df['range'] = pd.cut(df['days_since_last_call'],
                             bins=bins,
                             labels=labels)

        # Group by range and count. observed=False keeps buckets with 0 terminals too.
        stats = df.groupby('range', observed=False).size().reset_index(name='count')
        logger.info(f"Generated idle distribution statistics: {stats.to_dict(orient='records')}")

        response = {
            "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "data": stats.to_dict(orient='records')
        }

        # Cache the result for 30 seconds
        cache_set(cache_key, response, ttl=60)

        return jsonify(response)

    except Exception as e:
        logger.error(f"Error generating statistics for idle distribution: {e}")
        return jsonify({"error": "database error"}), 500
