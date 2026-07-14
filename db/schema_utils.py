import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)


def ensure_updated_on_column(conn):
    """
    Ensure that the 'updated_on' column exists in the 'terminals' table.
    If it does not exist, add the column.
    :param conn: SQLAlchemy connection object
    :return: None
    """
    column_exists = conn.execute(
        text("""
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'terminals'
              AND COLUMN_NAME = 'updated_on'
        """)
    ).scalar()

    if column_exists == 0:
        conn.execute(
            text("ALTER TABLE terminals ADD COLUMN updated_on DATETIME NULL")
        )
        logger.info("Added updated_on column to terminals table")


def ensure_decommission_queue_table(conn):
    """
    Ensure that the 'decommission_queue' table exists in the database.
    If it does not exist, create the table.
    :param conn: SQLAlchemy connection object
    :return: None
    """
    conn.execute(
        text("""
            CREATE TABLE IF NOT EXISTS decommission_queue (
                tid VARCHAR(20) PRIMARY KEY,
                queued_on DATETIME NOT NULL,
                delete_after DATETIME NOT NULL,
                FOREIGN KEY (tid) REFERENCES terminals(tid)
            )
        """)
    )
    logger.info("Ensured decommission_queue table exists")