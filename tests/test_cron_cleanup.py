import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLEANUP_FILE = PROJECT_ROOT / "crontab" / "cleanup_decommission.py"

spec = importlib.util.spec_from_file_location("cleanup_decommission", CLEANUP_FILE)
cleanup_decommission = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup_decommission)


class FakeMappingsResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class FakeConn:
    def __init__(self, expired_rows):
        self.expired_rows = expired_rows
        self.delete_order = []

    def execute(self, statement, params=None):
        sql = str(statement)

        if "SELECT tid" in sql and "FROM decommission_queue" in sql:
            return FakeMappingsResult(self.expired_rows)

        if "DELETE FROM decommission_queue" in sql:
            self.delete_order.append(("queue", params["tid"]))

        if "DELETE FROM terminals" in sql:
            self.delete_order.append(("terminal", params["tid"]))

        return FakeMappingsResult([])


class FakeBegin:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeEngine:
    def __init__(self, conn):
        self.conn = conn

    def begin(self):
        return FakeBegin(self.conn)


def test_cleanup_deletes_queue_row_before_terminal_row(monkeypatch):
    conn = FakeConn(expired_rows=[{"tid": "T0101001"}, {"tid": "T0101002"}])
    monkeypatch.setattr(cleanup_decommission, "engine", FakeEngine(conn))
    monkeypatch.setattr(
        cleanup_decommission,
        "ensure_decommission_queue_table",
        lambda current_conn: None,
    )

    cleanup_decommission.cleanup_decommissioned_terminals()

    assert conn.delete_order == [
        ("queue", "T0101001"),
        ("terminal", "T0101001"),
        ("queue", "T0101002"),
        ("terminal", "T0101002"),
    ]


def test_cleanup_does_nothing_when_no_expired_rows(monkeypatch):
    conn = FakeConn(expired_rows=[])
    monkeypatch.setattr(cleanup_decommission, "engine", FakeEngine(conn))
    monkeypatch.setattr(
        cleanup_decommission,
        "ensure_decommission_queue_table",
        lambda current_conn: None,
    )

    cleanup_decommission.cleanup_decommissioned_terminals()

    assert conn.delete_order == []
