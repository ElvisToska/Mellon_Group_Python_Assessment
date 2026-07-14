from flask import Flask

from app.routes import terminals


def make_test_app():
    return Flask(__name__)


def response_json(response_tuple):
    response, status_code = response_tuple
    return response.get_json(), status_code


def test_get_terminals_rejects_invalid_enabled_value(monkeypatch):
    app = make_test_app()
    monkeypatch.setattr(terminals, "cache_get", lambda key: None)

    with app.test_request_context("/terminals?enabled=maybe", method="GET"):
        body, status_code = response_json(terminals.get_terminals())

    assert status_code == 400
    assert "enabled" in body["error"]


def test_flag_terminal_requires_scenario_number(monkeypatch):
    app = make_test_app()
    monkeypatch.setattr(terminals, "cache_get", lambda key: None)

    with app.test_request_context("/terminals/T0101001/flag", method="POST", json={}):
        body, status_code = response_json(terminals.flag_terminal("T0101001"))

    assert status_code == 400
    assert body["error"] == "scenario_number is required"


def test_flag_terminal_rejects_empty_scenario_number(monkeypatch):
    app = make_test_app()
    monkeypatch.setattr(terminals, "cache_get", lambda key: None)

    with app.test_request_context(
        "/terminals/T0101001/flag",
        method="POST",
        json={"scenario_number": ""},
    ):
        body, status_code = response_json(terminals.flag_terminal("T0101001"))

    assert status_code == 400
    assert body["error"] == "scenario_number cannot be empty"


def test_create_terminal_from_template_requires_body_fields():
    app = make_test_app()

    with app.test_request_context("/terminals/from-template", method="POST", json={}):
        body, status_code = response_json(terminals.create_terminal_from_template())

    assert status_code == 400
    assert body["error"] == "template_id and mid are required"


def test_create_terminal_from_template_requires_mid_string():
    app = make_test_app()

    with app.test_request_context(
        "/terminals/from-template",
        method="POST",
        json={"template_id": 1, "mid": 123},
    ):
        body, status_code = response_json(terminals.create_terminal_from_template())

    assert status_code == 400
    assert body["error"] == "mid must be a string"


def test_create_terminal_from_template_rejects_invalid_template_id():
    app = make_test_app()

    with app.test_request_context(
        "/terminals/from-template",
        method="POST",
        json={"template_id": "not-a-number", "mid": "MID000101"},
    ):
        body, status_code = response_json(terminals.create_terminal_from_template())

    assert status_code == 400
    assert body["error"] == "template_id must be an integer"
