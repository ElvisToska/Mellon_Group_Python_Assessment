import logging
import sys
from datetime import datetime

from flask import Flask, jsonify, request, Blueprint
from sqlalchemy import text
from sqlalchemy.ext.asyncio import result

from db.cache import cache_clear_all, cache_get, cache_set, redis_client
from db.db_connection import engine
from db.schema_utils import ensure_updated_on_column, ensure_decommission_queue_table


logger = logging.getLogger(__name__)

terminals_bp = Blueprint("terminals", __name__)


# --- List terminals (cached) ----------------------------------------------
@terminals_bp.route('/terminals', methods=['GET'])
def get_terminals():
    """
    Get a list of terminals, optionally filtered by the 'enabled' query parameter.
    Retrieves the list from cache if available,
    otherwise queries the database and caches the result.
    It manages if the 'enabled' query parameter is provided, filtering the results accordingly.
    :return: JSON response containing the list of terminals
    """

    # Get the 'enabled' query parameter if exists, else None
    enabled = request.args.get('enabled')

    # Check cache first
    cache_key = f"terminals:list:{enabled}"
    cached = cache_get(cache_key)
    if cached is not None:
        return jsonify(cached)

    # Build the SQL query
    query = ("SELECT t.tid, m.mid, t.hardware_model, t.software_version, t.enabled, "
        "t.last_call_stamp AS last_call "
        "FROM terminals t "
        "JOIN merchants m ON t.merchant_id = m.id")
    params = {}

    # Add WHERE to the SQL query if 'enabled' parameter if exists
    if enabled is not None:
        if enabled.lower() == '1' or enabled.lower() == 'true':
            query += " WHERE t.enabled = 1"
        elif enabled.lower() == '0' or enabled.lower() == 'false':
            query += " WHERE t.enabled = 0"
        else:
            return jsonify({"error": "Invalid value for 'enabled'. Use 'true' or 'false'."}), 400
        logger.info(f"Filtering terminals by enabled={enabled}")

    # Execute the query and fetch results
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(query), params).mappings().all()
            logger.info(f"Fetched {len(rows)} terminals from the database with enabled={enabled}")

    except Exception as e:
        logger.error(f"Error fetching terminals: {e}")
        return jsonify({"error": "database error"}), 500

    result = []
    for row in rows:
        terminal = dict(row)

        terminal["enabled"] = bool(terminal["enabled"]) # Convert enabled to boolean for JSON response

        if terminal["last_call"] is not None:
            terminal["last_call"] = terminal["last_call"].strftime("%Y-%m-%dT%H:%M:%S") # Convert last_call to ISO format for JSON response

        result.append(terminal)

    cache_set(cache_key, result, ttl = 30)  # Cache for 30 seconds
    return jsonify(result)

# --- Get a specific terminal and return its details (cached) --------------------------
@terminals_bp.route('/terminals/<tid>', methods=['GET'])
def get_terminal(tid):
    """
    Get the details of a specific terminal by its TID.
    Retrieves the details from cache if available,
    otherwise queries the database and caches the result.
    :param tid: Terminal ID
    :return: JSON response containing the terminal details
    """

    # Check cache first
    cache_key = f"terminals:detail:{tid}"
    cached = cache_get(cache_key)
    if cached is not None:
        return jsonify(cached)

    # Execute the query and fetch results
    try:
        # get the terminal details from the database
        with engine.connect() as conn:
            terminal = conn.execute(
                text("SELECT * "
                     "FROM terminals "
                     "WHERE tid = :tid"),
                {"tid": tid}
            ).mappings().first()

            # If the terminal is not found, return a 404 error
            if terminal is None:
                logger.error(f"Terminal {tid} not found in the database")
                return jsonify({"error": "Terminal not found"}), 404
            logger.info(f"Fetched terminal {tid} from the database")

    except Exception as e:
        logger.error(f"Error fetching terminal {tid}: {e}")
        return jsonify({"error": "database error"}), 500

    result = dict(terminal)
    cache_set(cache_key, dict(terminal), ttl=30)  # Cache for 30 seconds
    return jsonify(result)


# --- Gets the terminals that needs to be upgraded (flagged) (cached) -------------------------
@terminals_bp.route('/terminals/flagged', methods=['GET'])
def get_flagged_terminals():
    """
    Get the list of terminals that are flagged for upgrade (i.e., have a non-null, non-empty, and non-zero scenario_number).
    Retrieves the list from cache if available, otherwise queries the database and caches the result
    :return: JSON response containing the list of flagged terminals
    """

    # Check cache first
    cache_key = "terminals:flagged"
    cached = cache_get(cache_key)
    if cached is not None:
        return jsonify(cached)

    # Execute the query and fetch results
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                # Returns terminals where the scenario_number is not NULL, not an empty string, and not '0'.
                text("SELECT * FROM terminals "
                     "WHERE scenario_number IS NOT NULL "
                     "AND scenario_number != '' "
                     "AND scenario_number != '0'")
            ).mappings().all()

            # If no flagged terminals are found, return a message indicating that
            if len(rows) == 0:
                logger.info("No flagged terminals found in the database")
                return jsonify({"message": "No flagged terminals found"}), 200
            logger.info(f"Fetched {len(rows)} flagged terminals from the database")

    except Exception as e:
        logger.error(f"Error fetching flagged terminals: {e}")
        return jsonify({"error": "database error"}), 500

    result = [dict(row) for row in rows]
    cache_set(cache_key, result, ttl=30)  # Cache for 30 seconds
    return jsonify(result)


# --- Flag a terminal for upgrade ----------------------------------------------
@terminals_bp.route('/terminals/<tid>/flag', methods=['POST'])
def flag_terminal(tid):
    """
    Flag a terminal for upgrade by setting its scenario_number.
    If the terminal is already flagged with the same scenario_number, it returns a conflict response.
    :param tid: Terminal ID
    :return: JSON response indicating the result of the operation
    """

    # check the request body for the scenario_number
    data = request.get_json(silent=True)
    if data is None or "scenario_number" not in data:
        logger.error(f"Missing scenario_number in request body for terminal {tid}.")
        return jsonify({"error": "scenario_number is required"}), 400

    # check if the scenario_number is empty
    scenario_number = str(data["scenario_number"])
    if scenario_number == "":
        logger.error(f"Empty scenario_number provided for terminal {tid}.")
        return jsonify({"error": "scenario_number cannot be empty"}), 400

    try:
        with engine.begin() as conn:
            #check if the 'updated_on' column exists, and add it if it doesn't
            ensure_updated_on_column(conn)

            terminal = conn.execute(
                text("SELECT scenario_number "
                     "FROM terminals "
                     "WHERE tid = :tid "
                     "FOR UPDATE"),  # Lock the row for update to prevent race conditions
                {"tid": tid}
            ).mappings().first()

            # If the terminal is not found, return a 404 error
            if terminal is None:
                logger.error(f"Terminal {tid} not found for flagging.")
                return jsonify({"error": "Terminal was not found"}), 404
            logger.info(f"Fetched terminal {tid} from the database for flagging.")

            old_scenario_number = terminal["scenario_number"]

            # Check if the terminal is already flagged with the same scenario_number
            if old_scenario_number == scenario_number:
                logger.error(f"Terminal {tid} is already flagged with scenario_number {scenario_number}.")
                return jsonify({
                    "message": "Terminal is already flagged with this scenario_number",
                    "tid": tid,
                    "scenario_number": scenario_number
                }), 409
            logger.info(f"Flagging terminal {tid}: changing scenario_number from {old_scenario_number} to {scenario_number}.")

            # Update the scenario_number and set the updated_on timestamp
            now = datetime.now()
            conn.execute(
                text("""
                     UPDATE terminals
                     SET scenario_number = :scenario_number,
                         updated_on      = :now
                     WHERE tid = :tid
                     """),
                {
                    "tid": tid,
                    "scenario_number": scenario_number,
                    "now": now
                }
            )
        logger.info(
            f"Terminal {tid} flagged: scenario_number changed "
            f"from {old_scenario_number} to {scenario_number} "
        )

        cache_clear_all()
        logger.info(f"Cache cleared after flagging terminal {tid}.")

        return jsonify({
            "message": "Terminal flagged successfully",
            "tid": tid,
            "old_scenario_number": old_scenario_number,
            "new_scenario_number": scenario_number
        }), 200

    except Exception as e:
        logger.error(f"Error flagging terminal {tid}: {e}")
        return jsonify({"error": "database error"}), 500



# --- Unflag a terminal (set scenario_number to '0') ----------------------------------------------
@terminals_bp.route('/terminals/<tid>/unflag', methods=['POST'])
def unflag_terminal(tid):
    """
    Unflag a terminal by setting its scenario_number to '0'.
    If the terminal is already unflagged, it returns a conflict response.
    :param tid: Terminal ID
    :return: JSON response indicating the result of the operation
    """

    try:
        with engine.begin() as conn:
            ensure_updated_on_column(conn)

            terminal = conn.execute(
                text("SELECT scenario_number "
                     "FROM terminals "
                     "WHERE tid = :tid"
                     " FOR UPDATE"),  # Lock the row for update to prevent race conditions
                {"tid": tid}
            ).mappings().first()

            # If the terminal is not found, return a 404 error
            if terminal is None:
                logger.error(f"Terminal {tid} not found for unflagging.")
                return jsonify({"error": "Terminal not found"}), 404
            logger.info(f"Fetched terminal {tid} from the database for unflagging.")

            old_scenario_number = terminal["scenario_number"]

            # Check if the terminal is already unflagged (scenario_number is None, empty, or '0')
            if old_scenario_number is None or old_scenario_number == "" or old_scenario_number == "0":
                logger.info(f"Terminal {tid} is already unflagged.")
                return jsonify({
                    "message": "Terminal is already unflagged",
                    "tid": tid,
                    "scenario_number": old_scenario_number
                }), 409

            # Update the scenario_number to '0' and set the updated_on timestamp
            now = datetime.now()
            conn.execute(
                text("""
                    UPDATE terminals
                    SET scenario_number = '0',
                        updated_on = :now
                    WHERE tid = :tid
                """),
                {"tid": tid, "now": now}
            )

        logger.info(
            f"Terminal {tid} unflagged: scenario_number changed "
            f"from {old_scenario_number} to 0"
        )

        cache_clear_all()
        logger.info(f"Cache cleared after unflagging terminal {tid}.")

        return jsonify({
            "message": "Terminal unflagged successfully",
            "tid": tid,
            "old_scenario_number": old_scenario_number,
            "new_scenario_number": "0"
        }), 200

    except Exception as e:
        logger.error(f"Error unflagging terminal {tid}: {e}")
        return jsonify({"error": "database error"}), 500



# --- Decommission a terminal (set enabled to 0) ----------------------------------------------
@terminals_bp.route('/terminals/<tid>/decommission', methods=['POST'])
def decommission_terminal(tid):
    """
    Decommission a terminal by setting its enabled status to 0 and adding it to the decommission_queue.
    If the terminal is already decommissioned, it returns a conflict response.
    :param tid: Terminal ID
    :return: JSON response indicating the result of the operation
    """

    try:
        with engine.begin() as conn:
            ensure_updated_on_column(conn)
            ensure_decommission_queue_table(conn)

            terminal = conn.execute(
                text("SELECT enabled "
                     "FROM terminals "
                     "WHERE tid = :tid"
                     " FOR UPDATE"),  # Lock the row for update to prevent race conditions
                {"tid": tid}
            ).mappings().first()

            # If the terminal is not found, return a 404 error
            if terminal is None:
                logger.error(f"Terminal {tid} not found for decommissioning.")
                return jsonify({"error": "Terminal not found"}), 404
            logger.info(f"Fetched terminal {tid} from the database for decommissioning.")

            # Check if the terminal is already decommissioned (enabled is 0)
            if terminal["enabled"] == 0:
                logger.error(f"Conflict error: terminal {tid} is already decommissioned.")
                return jsonify({
                    "message": "Terminal already decommissioned",
                    "tid": tid
                }), 409
            logger.info(f"Decommissioning terminal {tid}.")

            now = datetime.now()
            conn.execute(
                text("""
                    UPDATE terminals
                    SET enabled = 0,
                        updated_on = :now
                    WHERE tid = :tid
                """),
                {"tid": tid, "now": now}
            )
            logger.info(f"Terminal {tid} decommissioned successfully.")

            # Add the terminal to the decommission_queue with a delete_after date 3 days from now
            conn.execute(
                text("""
                     INSERT INTO decommission_queue (tid, queued_on, delete_after)
                     VALUES (:tid, :queued_on, DATE_ADD(:queued_on, INTERVAL 3 DAY))
                     """),
                {
                    "tid": tid,
                    "queued_on": now
                }
            )
            logger.info(f"Terminal {tid} added to decommission_queue with delete_after set to 3 days from now.")

            # Retrieve the queued terminal details to return in the response
            queued_terminal = conn.execute(
                text("""
                     SELECT tid, queued_on, delete_after
                     FROM decommission_queue
                     WHERE tid = :tid
                     """),
                {"tid": tid}
            ).mappings().first()
        logger.info(f"Terminal {tid} decommissioned and added to decommission_queue.")


        cache_clear_all()
        logger.info(f"Cache cleared after decommissioning terminal {tid}.")

        return jsonify({
            "message": "Terminal decommissioned successfully",
            "tid": queued_terminal["tid"],
            "queued_on": queued_terminal["queued_on"].isoformat(),
            "delete_after": queued_terminal["delete_after"].isoformat()
        }), 200

    except Exception as e:
        logger.error(f"Error decommissioning terminal {tid}: {e}")
        return jsonify({"error": "database error"}), 500


# --- Get the list of decommissioned terminals (from decommission_queue) --------------------
@terminals_bp.route('/terminals/decommissioned', methods=['GET'])
def decommission_terminals():
    """
    Get the list of decommissioned terminals from the decommission_queue.
    Retrieves the list from cache if available,
    otherwise queries the database and caches the result.
    Then , it calculates the days remaining until the terminal is deleted based on the delete_after date.
    :return: JSON response containing the list of decommissioned terminals with their details and days remaining
    """

    # Check cache first
    cache_key = "terminals:decommissioned:list"
    cached = cache_get(cache_key)
    if cached is not None:
        return jsonify(cached)

    try:
        with engine.begin() as conn:
            ensure_decommission_queue_table(conn)

            rows = conn.execute(
                text("""
                     SELECT t.tid, m.mid, t.hardware_model, t.software_version,
                            t.enabled, dq.queued_on, dq.delete_after
                     FROM decommission_queue dq
                              JOIN terminals t ON dq.tid = t.tid
                              JOIN merchants m ON t.merchant_id = m.id
                     ORDER BY dq.delete_after ASC
                     """)
            ).mappings().all()

            result = []
            now = datetime.now()

            for row in rows:
                days_remaining = (row["delete_after"] - now).days

                if days_remaining < 0:
                    days_remaining = 0

                result.append({
                    "tid": row["tid"],
                    "mid": row["mid"],
                    "hardware_model": row["hardware_model"],
                    "software_version": row["software_version"],
                    "enabled": bool(row["enabled"]),
                    "queued_on": row["queued_on"].isoformat(),
                    "delete_after": row["delete_after"].isoformat(),
                    "days_remaining": days_remaining
                })

            if result.__len__() == 0:    
                logger.info("No decommissioned terminals found.")
                return jsonify({"message": "Does not exist a decommissioned terminal."}), 200
            logger.info(f"Fetched {len(result)} decommissioned terminals from the database.")

            cache_set(cache_key, result, ttl=30)  # Cache for 30 seconds

            return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error fetching decommissioned terminals: {e}")
        return jsonify({"error": "database error"}), 500


# --- Create a new terminal from a template for a merchant ------------------------------
@terminals_bp.route("/terminals/from-template", methods=["POST"])
def create_terminal_from_template():
    """
    Create a new terminal for a merchant based on a specified template.
    The request body must contain the 'template_id' and 'mid' (merchant ID).
    The function checks if the template and merchant exist, generates a new terminal ID (tid),
    and inserts the new terminal into the database.
    :return: JSON response containing the details of the newly created terminal
    """
    data = request.get_json(silent=True) # get the request body as JSON, return None if invalid JSON

    # for missing elements
    if data is None or "template_id" not in data or "mid" not in data:
        logger.error("Missing template_id or mid in request body")
        return jsonify({"error": "template_id and mid are required"}), 400

    # for checking if mid is a string
    if not isinstance(data["mid"], str):
        logger.error("Invalid mid. It must be a string.")
        return jsonify({"error": "mid must be a string"}), 400

    # for converting an invalid template_id to int if possible, else return an error
    try:
        template_id = int(data["template_id"])
    except (ValueError, TypeError):
        logger.error("Invalid template_id. It must be an integer.")
        return jsonify({"error": "template_id must be an integer"}), 400


    try:
        mid = data.get("mid")

        with engine.begin() as conn:

            # check if the template exists
            template = conn.execute(
                text("SELECT id, hardware_model, hardware_family "
                     "FROM templates "
                     "WHERE id = :id"),
                {"id": template_id}
            ).mappings().first()
            if template is None:
                logger.error(f"Template with ID {template_id} not found")
                return jsonify({"error": "template not found"}), 404
            logger.info(f"Got template with ID {template_id} from the database")

            # check if the merchant exists
            merchant = conn.execute(
                text("SELECT id, mid "
                     "FROM merchants "
                     "WHERE mid = :mid "
                     "FOR UPDATE"),
                {"mid": mid}
            ).mappings().first()
            if merchant is None:
                logger.error(f"Merchant with MID {mid} not found")
                return jsonify({"error": "merchant not found"}), 404
            logger.info(f"Got merchant with MID {mid} from the database")

            # Creating new tid for new teminal:
            prefix = "T" + mid[-4:]

            # check the last terminal for this merchant and get its tid
            last_terminal = conn.execute(
                text("SELECT tid FROM terminals "
                     "WHERE merchant_id = :merchant_id "
                     "ORDER BY tid DESC LIMIT 1 "
                     "FOR UPDATE"),
                {"merchant_id": merchant["id"]}
            ).mappings().first()

            # if the merchant has not terminals yet
            if last_terminal is None:
                new_tid = f"{prefix}001"
            else:
                last_tid = last_terminal["tid"]
                last_number = int(last_tid[-3:])
                new_number = last_number + 1
                new_tid = f"{prefix}{new_number:03d}"

            # insert the new terminal into the terminals table
            conn.execute(
                text("INSERT INTO terminals (tid, merchant_id, template_id, hardware_model, hardware_family, last_call_stamp) "
                     "VALUES (:tid, :merchant_id, :template_id, :hardware_model, :hardware_family, :last_call_stamp)"),
                {
                    "tid": new_tid,
                    "merchant_id": merchant["id"],
                    "template_id": template_id,
                    "hardware_model": template["hardware_model"],
                    "hardware_family": template["hardware_family"],
                    "last_call_stamp": datetime.now()
                }
            )
            logger.info(f"Created new terminal with TID {new_tid} for merchant MID {mid} using template ID {template_id}")

        cache_clear_all()

        return jsonify(
            {
                "tid": new_tid,
                "mid": mid,
                "template_id": template_id,
                "hardware_model": template["hardware_model"],
                "hardware_family": template["hardware_family"]
            }
        ), 201

    except Exception as e:
        logger.error(f"Error fetching template with ID {template_id}: {e}")
        return jsonify({"error": "database error"}), 500
