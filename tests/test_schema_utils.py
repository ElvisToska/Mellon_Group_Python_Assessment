from db import schema_utils


class FakeResult:
    def __init__(self, scalar_value=None):
        self.scalar_value = scalar_value

    def scalar(self):
        return self.scalar_value


class FakeConn:
    def __init__(self, column_exists=0):
        self.column_exists = column_exists
        self.statements = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)

        if "INFORMATION_SCHEMA.COLUMNS" in sql:
            return FakeResult(self.column_exists)

        return FakeResult()


def test_ensure_updated_on_column_does_not_alter_when_column_exists():
    conn = FakeConn(column_exists=1)

    schema_utils.ensure_updated_on_column(conn)

    joined_sql = "\n".join(conn.statements)
    assert "INFORMATION_SCHEMA.COLUMNS" in joined_sql
    assert "ALTER TABLE terminals ADD COLUMN updated_on" not in joined_sql


def test_ensure_updated_on_column_adds_column_when_missing():
    conn = FakeConn(column_exists=0)

    schema_utils.ensure_updated_on_column(conn)

    joined_sql = "\n".join(conn.statements)
    assert "INFORMATION_SCHEMA.COLUMNS" in joined_sql
    assert "ALTER TABLE terminals ADD COLUMN updated_on DATETIME NULL" in joined_sql


def test_ensure_decommission_queue_table_is_idempotent_create_table():
    conn = FakeConn()

    schema_utils.ensure_decommission_queue_table(conn)

    joined_sql = "\n".join(conn.statements)
    assert "CREATE TABLE IF NOT EXISTS decommission_queue" in joined_sql
    assert "tid VARCHAR(20) PRIMARY KEY" in joined_sql
    assert "FOREIGN KEY (tid) REFERENCES terminals(tid)" in joined_sql
