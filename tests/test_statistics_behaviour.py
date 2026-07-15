import re
from datetime import datetime, timedelta

from flask import Flask

from app.routes import statistics


def make_test_app():
    return Flask(__name__)


class FakeResult:
    def __init__(self, rows, columns):
        self.rows = rows
        self.columns = columns
        self.rowcount = len(rows)

    def fetchall(self):
        return self.rows

    def keys(self):
        return self.columns


class FakeConn:
    def __init__(self, rows, columns):
        self.rows = rows
        self.columns = columns

    def execute(self, statement, params=None):
        return FakeResult(self.rows, self.columns)


class FakeContext:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeEngine:
    def __init__(self, conn):
        self.conn = conn

    def connect(self):
        return FakeContext(self.conn)


def test_statistics_by_hardware_returns_expected_shape_and_timestamp(monkeypatch):
    app = make_test_app()
    conn = FakeConn(
        rows=[("Desk2600",), ("Desk2600",), ("iwl220",)],
        columns=["hardware_model"],
    )
    cached_payloads = []

    monkeypatch.setattr(statistics, "engine", FakeEngine(conn))
    monkeypatch.setattr(statistics, "cache_get", lambda key: None)
    monkeypatch.setattr(
        statistics,
        "cache_set",
        lambda key, value, ttl=60: cached_payloads.append((key, value, ttl)),
    )

    with app.test_request_context("/statistics/by-hardware"):
        response = statistics.statistics_by_hardware()

    body = response.get_json()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", body["generated_at"])
    assert {"hardware_model": "Desk2600", "count": 2} in body["data"]
    assert {"hardware_model": "iwl220", "count": 1} in body["data"]
    assert cached_payloads[0][0] == "statistics:by-hardware"
    assert cached_payloads[0][2] == 60


def test_statistics_by_state_returns_json_serializable_counts(monkeypatch):
    app = make_test_app()
    conn = FakeConn(rows=[(1,), (1,), (0,)], columns=["enabled"])

    monkeypatch.setattr(statistics, "engine", FakeEngine(conn))
    monkeypatch.setattr(statistics, "cache_get", lambda key: None)
    monkeypatch.setattr(statistics, "cache_set", lambda key, value, ttl=60: None)

    with app.test_request_context("/statistics/by-state"):
        response = statistics.statistics_by_state()

    body = response.get_json()
    assert body["active"] == 2
    assert body["inactive"] == 1
    assert body["total"] == 3


def test_statistics_by_hardware_family_groups_rows_with_pandas(monkeypatch):
    app = make_test_app()
    conn = FakeConn(
        rows=[("Desk",), ("Desk",), ("Android",)],
        columns=["hardware_family"],
    )

    monkeypatch.setattr(statistics, "engine", FakeEngine(conn))
    monkeypatch.setattr(statistics, "cache_get", lambda key: None)
    monkeypatch.setattr(statistics, "cache_set", lambda key, value, ttl=60: None)

    with app.test_request_context("/statistics/by-hardware-family"):
        response = statistics.statistics_by_hardware_family()

    body = response.get_json()
    assert {"hardware_family": "Desk", "count": 2} in body["data"]
    assert {"hardware_family": "Android", "count": 1} in body["data"]


def test_statistics_idle_distribution_groups_rows_with_pandas(monkeypatch):
    app = make_test_app()
    now = datetime.now()
    conn = FakeConn(
        rows=[
            (now,),
            (now - timedelta(days=2),),
            (now - timedelta(days=20),),
            (now - timedelta(days=100),),
        ],
        columns=["last_call_stamp"],
    )

    monkeypatch.setattr(statistics, "engine", FakeEngine(conn))
    monkeypatch.setattr(statistics, "cache_get", lambda key: None)
    monkeypatch.setattr(statistics, "cache_set", lambda key, value, ttl=60: None)

    with app.test_request_context("/statistics/idle-distribution"):
        response = statistics.statistics_idle_distribution()

    body = response.get_json()
    counts = {item["range"]: item["count"] for item in body["data"]}
    assert counts["Σήμερα"] == 1
    assert counts["1-7 μέρες"] == 1
    assert counts["8-30 μέρες"] == 1
    assert counts["31-90 μέρες"] == 0
    assert counts["90+ μέρες"] == 1
