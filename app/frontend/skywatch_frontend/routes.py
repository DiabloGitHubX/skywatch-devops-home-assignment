"""Frontend routes and backend HTTP communication."""

import os

import requests
from flask import Blueprint, render_template, request

frontend = Blueprint("frontend", __name__)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:5001").rstrip("/")

REQUEST_TIMEOUT = (3, 7)


@frontend.get("/healthz")
def health():
    """Liveness endpoint for Kubernetes."""
    return {"status": "ok"}, 200


@frontend.get("/")
def index():
    """Display the weather search page."""

    city = request.args.get("city", "").strip()
    weather = None
    error = None

    if city:
        try:
            response = requests.get(
                f"{BACKEND_URL}/api/weather",
                params={"city": city},
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code == 200:
                weather = response.json()
            elif response.status_code == 404:
                error = "City not found. Please try another city."
            elif response.status_code == 400:
                error = "Please enter a valid city name."
            else:
                error = "Weather service is temporarily unavailable."

        except requests.Timeout:
            error = "Weather request timed out. Please try again."
        except (requests.RequestException, ValueError):
            error = "Unable to retrieve weather information."

    return render_template(
        "index.html",
        city=city,
        weather=weather,
        error=error,
    )
