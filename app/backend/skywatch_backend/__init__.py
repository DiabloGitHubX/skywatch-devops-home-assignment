from flask import Flask

from .api import api


def create_app() -> Flask:
    """Create and configure the SkyWatch backend application."""
    app = Flask(__name__)

    app.register_blueprint(api)

    return app
