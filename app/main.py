import logging
import sys

from flask import Flask, jsonify

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
    def method_not_allowed(error):
        return jsonify({"error": "method not allowed"}), 405
    return app

app = create_app()

if __name__ == "__main__":

    app.run(host="0.0.0.0", port=5000)
