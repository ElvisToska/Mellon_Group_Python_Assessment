from datetime import datetime, timedelta

from flask import Flask

from app.routes import health, reports, templates, terminals


def make_test_app():
    return Flask(__name__)


def unpack(response_tuple):
    response, status_code = response_tuple
    return response.get_json(), status_code


class FakeResult:
    def __init__(self, rows=None, first_row=None):
        self.rows = rows or []
        self.first_row = first_row

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.first_row


class FakeConn:
    def __init__(self, handler):
        self.handler = handler
        self.statements = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append((sql, params or {}))
        return self.handler(sql, params or {})


class FakeContext:
    def __init__(self, conn=None, exc=None):
        self.conn = conn
        self.exc = exc

    def __enter__(self):
        if self.exc:
            raise self.exc
        return self.conn

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeEngine:
    def __init__(self, conn=None, exc=None):
        self.conn = conn
        self.exc = exc

    def connect(self):
        return FakeContext(self.conn, self.exc)

    def begin(self):
        return FakeContext(self.conn, self.exc)


class FakeRedis:
    def __init__(self, exc=None):
        self.exc = exc

    def ping(self):
        if self.exc:
            raise self.exc
        return True


def test_health_returns_200_when_database_and_redis_are_ok(monkeypatch):
    app = make_test_app()
    conn = FakeConn(lambda sql, params: FakeResult())
    monkeypatch.setattr(health, "engine", FakeEngine(conn))
    monkeypatch.setattr(health, "redis_client", FakeRedis())

    with app.test_request_context("/health"):
        body, status_code = unpack(health.health())

    assert status_code == 200
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["cache"] == "ok"


def test_health_returns_503_when_redis_is_down(monkeypatch):
    app = make_test_app()
    conn = FakeConn(lambda sql, params: FakeResult())
    monkeypatch.setattr(health, "engine", FakeEngine(conn))
    monkeypatch.setattr(health, "redis_client", FakeRedis(RuntimeError("down")))

    with app.test_request_context("/health"):
        body, status_code = unpack(health.health())

    assert status_code == 503
    assert body["status"] == "degraded"
    assert body["database"] == "ok"
    assert "error:" in body["cache"]


def test_get_terminals_returns_database_rows_and_sets_cache(monkeypatch):
    app = make_test_app()
    rows = [
        {
            "tid": "T0101001",
            "mid": "MID000101",
            "hardware_model": "Desk2600",
            "software_version": "12.4.0",
            "enabled": 1,
            "last_call": datetime(2026, 7, 1, 10, 0, 0),
        }
    ]
    conn = FakeConn(lambda sql, params: FakeResult(rows=rows))
    cached_payloads = []
    monkeypatch.setattr(terminals, "engine", FakeEngine(conn))
    monkeypatch.setattr(terminals, "cache_get", lambda key: None)
    monkeypatch.setattr(
        terminals,
        "cache_set",
        lambda key, value, ttl=30: cached_payloads.append((key, value, ttl)),
    )

    with app.test_request_context("/terminals"):
        response = terminals.get_terminals()

    body = response.get_json()
    assert body[0]["tid"] == "T0101001"
    assert body[0]["mid"] == "MID000101"
    assert body[0]["enabled"] is True
    assert body[0]["last_call"] == "2026-07-01T10:00:00"
    assert cached_payloads[0][0] == "terminals:list:None"
    assert cached_payloads[0][2] == 30


def test_get_terminals_returns_500_when_database_fails(monkeypatch):
    app = make_test_app()
    monkeypatch.setattr(terminals, "engine", FakeEngine(exc=RuntimeError("db down")))
    monkeypatch.setattr(terminals, "cache_get", lambda key: None)

    with app.test_request_context("/terminals"):
        body, status_code = unpack(terminals.get_terminals())

    assert status_code == 500
    assert body["error"] == "database error"


def test_get_terminal_returns_404_when_tid_does_not_exist(monkeypatch):
    app = make_test_app()
    conn = FakeConn(lambda sql, params: FakeResult(first_row=None))
    monkeypatch.setattr(terminals, "engine", FakeEngine(conn))
    monkeypatch.setattr(terminals, "cache_get", lambda key: None)

    with app.test_request_context("/terminals/NOPE"):
        body, status_code = unpack(terminals.get_terminal("NOPE"))

    assert status_code == 404
    assert body["error"] == "Terminal not found"


def test_flag_terminal_success_updates_row_and_clears_cache(monkeypatch):
    app = make_test_app()
    cleared = []

    def handler(sql, params):
        if "SELECT scenario_number" in sql:
            return FakeResult(first_row={"scenario_number": "0"})
        return FakeResult()

    conn = FakeConn(handler)
    monkeypatch.setattr(terminals, "engine", FakeEngine(conn))
    monkeypatch.setattr(terminals, "ensure_updated_on_column", lambda current_conn: None)
    monkeypatch.setattr(terminals, "cache_clear_all", lambda: cleared.append(True))

    with app.test_request_context(
        "/terminals/T0101001/flag",
        method="POST",
        json={"scenario_number": "5"},
    ):
        body, status_code = unpack(terminals.flag_terminal("T0101001"))

    assert status_code == 200
    assert body["old_scenario_number"] == "0"
    assert body["new_scenario_number"] == "5"
    assert cleared == [True]
    assert any("UPDATE terminals" in sql for sql, _ in conn.statements)


def test_flag_terminal_returns_409_when_scenario_is_already_the_same(monkeypatch):
    app = make_test_app()
    cleared = []

    conn = FakeConn(lambda sql, params: FakeResult(first_row={"scenario_number": "5"}))
    monkeypatch.setattr(terminals, "engine", FakeEngine(conn))
    monkeypatch.setattr(terminals, "ensure_updated_on_column", lambda current_conn: None)
    monkeypatch.setattr(terminals, "cache_clear_all", lambda: cleared.append(True))

    with app.test_request_context(
        "/terminals/T0101001/flag",
        method="POST",
        json={"scenario_number": "5"},
    ):
        body, status_code = unpack(terminals.flag_terminal("T0101001"))

    assert status_code == 409
    assert body["message"] == "Terminal is already flagged with this scenario_number"
    assert cleared == []
    assert not any("UPDATE terminals" in sql for sql, _ in conn.statements)


def test_unflag_terminal_returns_404_when_tid_does_not_exist(monkeypatch):
    app = make_test_app()
    conn = FakeConn(lambda sql, params: FakeResult(first_row=None))
    monkeypatch.setattr(terminals, "engine", FakeEngine(conn))
    monkeypatch.setattr(terminals, "ensure_updated_on_column", lambda current_conn: None)

    with app.test_request_context("/terminals/NOPE/unflag", method="POST"):
        body, status_code = unpack(terminals.unflag_terminal("NOPE"))

    assert status_code == 404
    assert body["error"] == "Terminal not found"


def test_unflag_terminal_returns_409_when_terminal_is_already_unflagged(monkeypatch):
    app = make_test_app()
    cleared = []

    conn = FakeConn(lambda sql, params: FakeResult(first_row={"scenario_number": "0"}))
    monkeypatch.setattr(terminals, "engine", FakeEngine(conn))
    monkeypatch.setattr(terminals, "ensure_updated_on_column", lambda current_conn: None)
    monkeypatch.setattr(terminals, "cache_clear_all", lambda: cleared.append(True))

    with app.test_request_context("/terminals/T0101001/unflag", method="POST"):
        body, status_code = unpack(terminals.unflag_terminal("T0101001"))

    assert status_code == 409
    assert body["message"] == "Terminal is already unflagged"
    assert cleared == []
    assert not any("UPDATE terminals" in sql for sql, _ in conn.statements)


def test_decommission_terminal_returns_409_when_already_disabled(monkeypatch):
    app = make_test_app()
    conn = FakeConn(lambda sql, params: FakeResult(first_row={"enabled": 0}))
    monkeypatch.setattr(terminals, "engine", FakeEngine(conn))
    monkeypatch.setattr(terminals, "ensure_updated_on_column", lambda current_conn: None)
    monkeypatch.setattr(terminals, "ensure_decommission_queue_table", lambda current_conn: None)

    with app.test_request_context("/terminals/T0101001/decommission", method="POST"):
        body, status_code = unpack(terminals.decommission_terminal("T0101001"))

    assert status_code == 409
    assert body["message"] == "Terminal already decommissioned"


def test_wrong_method_returns_generic_405():
    from app.main import create_app

    app = create_app()
    client = app.test_client()

    response = client.post("/terminals")
    body = response.get_json()

    assert response.status_code == 405
    assert body["error"] == "method not allowed"


def test_decommission_terminal_success_queues_terminal_and_clears_cache(monkeypatch):
    app = make_test_app()
    cleared = []
    queued_on = datetime(2026, 7, 12, 10, 0, 0)
    delete_after = queued_on + timedelta(days=3)

    def handler(sql, params):
        if "SELECT enabled" in sql:
            return FakeResult(first_row={"enabled": 1})
        if "SELECT tid, queued_on, delete_after" in sql:
            return FakeResult(
                first_row={
                    "tid": params["tid"],
                    "queued_on": queued_on,
                    "delete_after": delete_after,
                }
            )
        return FakeResult()

    conn = FakeConn(handler)
    monkeypatch.setattr(terminals, "engine", FakeEngine(conn))
    monkeypatch.setattr(terminals, "ensure_updated_on_column", lambda current_conn: None)
    monkeypatch.setattr(terminals, "ensure_decommission_queue_table", lambda current_conn: None)
    monkeypatch.setattr(terminals, "cache_clear_all", lambda: cleared.append(True))

    with app.test_request_context("/terminals/T0101001/decommission", method="POST"):
        body, status_code = unpack(terminals.decommission_terminal("T0101001"))

    assert status_code == 200
    assert body["tid"] == "T0101001"
    assert body["delete_after"] == "2026-07-15T10:00:00"
    assert cleared == [True]
    assert any("INSERT INTO decommission_queue" in sql for sql, _ in conn.statements)


def test_create_terminal_from_template_returns_404_when_template_missing(monkeypatch):
    app = make_test_app()

    def handler(sql, params):
        if "FROM templates" in sql:
            return FakeResult(first_row=None)
        return FakeResult()

    monkeypatch.setattr(terminals, "engine", FakeEngine(FakeConn(handler)))

    with app.test_request_context(
        "/terminals/from-template",
        method="POST",
        json={"template_id": 1, "mid": "MID000101"},
    ):
        body, status_code = unpack(terminals.create_terminal_from_template())

    assert status_code == 404
    assert body["error"] == "template not found"


def test_create_terminal_from_template_returns_404_when_merchant_missing(monkeypatch):
    app = make_test_app()

    def handler(sql, params):
        if "FROM templates" in sql:
            return FakeResult(
                first_row={
                    "id": 1,
                    "hardware_model": "Desk2600",
                    "hardware_family": "Android",
                }
            )
        if "FROM merchants" in sql:
            return FakeResult(first_row=None)
        return FakeResult()

    monkeypatch.setattr(terminals, "engine", FakeEngine(FakeConn(handler)))

    with app.test_request_context(
        "/terminals/from-template",
        method="POST",
        json={"template_id": 1, "mid": "MID000101"},
    ):
        body, status_code = unpack(terminals.create_terminal_from_template())

    assert status_code == 404
    assert body["error"] == "merchant not found"


def test_create_terminal_from_template_success_uses_next_tid(monkeypatch):
    app = make_test_app()
    cleared = []

    def handler(sql, params):
        if "FROM templates" in sql:
            return FakeResult(
                first_row={
                    "id": 1,
                    "hardware_model": "Desk2600",
                    "hardware_family": "Android",
                }
            )
        if "FROM merchants" in sql:
            return FakeResult(first_row={"id": 1, "mid": "MID000101"})
        if "SELECT tid FROM terminals" in sql:
            return FakeResult(first_row={"tid": "T0101006"})
        return FakeResult()

    conn = FakeConn(handler)
    monkeypatch.setattr(terminals, "engine", FakeEngine(conn))
    monkeypatch.setattr(terminals, "cache_clear_all", lambda: cleared.append(True))

    with app.test_request_context(
        "/terminals/from-template",
        method="POST",
        json={"template_id": 1, "mid": "MID000101"},
    ):
        body, status_code = unpack(terminals.create_terminal_from_template())

    assert status_code == 201
    assert body["tid"] == "T0101007"
    assert body["template_id"] == 1
    assert cleared == [True]
    assert any("INSERT INTO terminals" in sql for sql, _ in conn.statements)


def test_list_templates_returns_rows(monkeypatch):
    app = make_test_app()
    rows = [
        {
            "id": 1,
            "template_name": "Restaurant Template",
            "hardware_model": "Desk2600",
            "hardware_family": "Desk",
        }
    ]
    conn = FakeConn(lambda sql, params: FakeResult(rows=rows))
    monkeypatch.setattr(templates, "engine", FakeEngine(conn))
    monkeypatch.setattr(templates, "cache_get", lambda key: None)

    with app.test_request_context("/templates"):
        body, status_code = unpack(templates.list_templates())

    assert status_code == 200
    assert body == rows


def test_get_template_returns_404_when_missing(monkeypatch):
    app = make_test_app()
    conn = FakeConn(lambda sql, params: FakeResult(first_row=None))
    monkeypatch.setattr(templates, "engine", FakeEngine(conn))
    monkeypatch.setattr(templates, "cache_get", lambda key: None)

    with app.test_request_context("/templates/999"):
        body, status_code = unpack(templates.get_template(999))

    assert status_code == 404
    assert body["error"] == "template not found"


def test_terminals_basic_csv_returns_csv(monkeypatch):
    app = make_test_app()
    rows = [
        {
            "tid": "T0101001",
            "mid": "MID000101",
            "hardware_model": "Desk2600",
            "software_version": "12.4.0",
            "enabled": 1,
            "last_call_stamp": datetime(2026, 7, 1, 10, 0, 0),
        }
    ]
    conn = FakeConn(lambda sql, params: FakeResult(rows=rows))
    monkeypatch.setattr(reports, "engine", FakeEngine(conn))

    with app.test_request_context("/reports/terminals_basic.csv"):
        response = reports.terminals_basic_csv()

    csv_text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.content_type.startswith("text/csv")
    assert "tid,mid,hardware_model,software_version,enabled,last_call" in csv_text
    assert "T0101001,MID000101,Desk2600,12.4.0,true,2026-07-01T10:00:00" in csv_text


def test_terminals_basic_csv_returns_500_when_database_fails(monkeypatch):
    app = make_test_app()
    monkeypatch.setattr(reports, "engine", FakeEngine(exc=RuntimeError("db down")))

    with app.test_request_context("/reports/terminals_basic.csv"):
        body, status_code = unpack(reports.terminals_basic_csv())

    assert status_code == 500
    assert body["error"] == "database error"
