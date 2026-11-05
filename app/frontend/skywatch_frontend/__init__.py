"""SkyWatch frontend application."""

from flask import Flask

from .routes import frontend


def create_app() -> Flask:
    """Create the Flask frontend application."""
    app = Flask(__name__)

    app.register_blueprint(frontend)

    return app
