def test_create_app_registers_all_expected_routes():
    from app.main import create_app

    app = create_app()
    routes = {rule.rule for rule in app.url_map.iter_rules()}

    assert "/health" in routes
    assert "/terminals" in routes
    assert "/terminals/flagged" in routes
    assert "/terminals/decommissioned" in routes
    assert "/terminals/from-template" in routes
    assert "/templates" in routes
    assert "/statistics/by-hardware" in routes
