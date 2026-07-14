import os

from sqlalchemy import create_engine

CONN = (
    f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT', '3306')}"
    f"/{os.getenv('DB_NAME')}?charset=utf8mb4"
)

engine = create_engine(CONN, pool_pre_ping=True)


