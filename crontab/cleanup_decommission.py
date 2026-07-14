import logging
import sys
from datetime import datetime

from sqlalchemy import text

from db.db_connection import engine
from db.schema_utils import ensure_decommission_queue_table

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s - %(message)s",
)

logger = logging.getLogger(__name__)


def cleanup_decommissioned_terminals():
    try:
        with engine.begin() as conn:
            ensure_decommission_queue_table(conn)

            now = datetime.now()
            expired_rows = conn.execute(
                text("""
                    SELECT tid
                    FROM decommission_queue
                    WHERE delete_after < :now
                """),
                {"now": now}
            ).mappings().all()

            if not expired_rows:
                logger.info("No expired decommissioned terminals found.")
                return

            deleted_count = 0
            for row in expired_rows:
                tid = row["tid"]

                # Delete from queue first , decommission_queue has FK to terminals.
                conn.execute(
                    text("DELETE FROM decommission_queue WHERE tid = :tid"),
                    {"tid": tid}
                )
                conn.execute(
                    text("DELETE FROM terminals WHERE tid = :tid"),
                    {"tid": tid}
                )
                deleted_count += 1
                logger.info(f"Deleted expired decommissioned terminal {tid}")

            logger.info(f"Cleanup finished. Deleted {deleted_count} terminals.")

    except Exception as e:
        logger.error(f"Error during decommission cleanup: {e}")
        raise


if __name__ == "__main__":
    cleanup_decommissioned_terminals()
