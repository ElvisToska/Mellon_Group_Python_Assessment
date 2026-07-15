import logging
import sys

from flask import Flask, jsonify, request

from app.routes.terminals import *
from app.routes.templates import templates_bp
from app.routes.statistics import statistics_bp
from app.routes.reports import reports_bp
from app.routes.health import health_bp

# putting the loggings in stdout
# this applies also to the other routes/ files
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_app():
    """
    Here the flask app is initialized
    Because of multiple branches , each branch was separated with help of .Blueprint
    In /routes/ folder are the implementations of each endpoint
    """
    app = Flask(__name__)
    app.json.ensure_ascii = False # for ascii
    app.json.sort_keys = False  # does not return results based on alphabetical order

    app.register_blueprint(health_bp) # /routes/health.py
    app.register_blueprint(terminals_bp) # /routes/terminals.py
    app.register_blueprint(templates_bp) # /routes/templates.py
    app.register_blueprint(statistics_bp) # /routes/statistics.py
    app.register_blueprint(reports_bp) # /routes/reports.py

    # in case of wrong method called, return 405 error
    @app.errorhandler(405)
    def method_not_allowed(error=None, allowed_methods=None):
        if allowed_methods is None:
            allowed_methods = getattr(error, "valid_methods", []) or []

        # getting what methods are allowed
        allowed_methods = [
            method for method in allowed_methods
            if method not in ("HEAD", "OPTIONS")
        ]

        return jsonify({
            "error": "method not allowed",
            "method_used": request.method, # the method that was used in the request
            "allowed_methods": sorted(allowed_methods)
        }), 405

    @app.before_request
    def method_not_allowed_for_static_routes():
        """
        its purpose is mostly for /terminals/from_template and /terminals/<tid>
        when accidentally made a GET request instead of POST on /terminals/from_template
        flask will return 404 error because it redirects at /terminals/<tid>,
        but the correct response should be 405 error
        :return: 405 error
        """
        requested_path = request.path.rstrip("/") or "/"
        allowed_methods = set()

        for rule in app.url_map.iter_rules():
            rule_path = rule.rule.rstrip("/") or "/"
            if "<" not in rule.rule and rule_path == requested_path:
                allowed_methods.update(rule.methods)

        if allowed_methods and request.method not in allowed_methods:
            return method_not_allowed(allowed_methods=allowed_methods)

    return app

app = create_app()

if __name__ == "__main__":

    app.run(host="0.0.0.0", port=5000)
