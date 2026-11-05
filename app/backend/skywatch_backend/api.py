"""HTTP routes for the SkyWatch backend."""

from flask import Blueprint, jsonify, request

from .weather import (
    CityNotFoundError,
    WeatherServiceError,
    WeatherTimeoutError,
    get_weather,
)

api = Blueprint("api", __name__)

MAX_CITY_LENGTH = 100


@api.get("/healthz")
def health():
    """Liveness endpoint for Kubernetes."""
    return jsonify({"status": "ok"}), 200


@api.get("/readyz")
def readiness():
    """Readiness endpoint for Kubernetes."""
    return jsonify({"status": "ready"}), 200


@api.get("/api/weather")
def weather():
    """Return current weather for the requested city."""

    city = request.args.get("city", "").strip()

    if not city:
        return jsonify({"error": "City parameter is required"}), 400

    if len(city) > MAX_CITY_LENGTH:
        return jsonify({"error": "City name exceeds maximum length"}), 400

    try:
        result = get_weather(city)
        return jsonify(result), 200

    except CityNotFoundError:
        return jsonify({"error": "City not found"}), 404

    except WeatherTimeoutError:
        return jsonify({"error": "Weather provider timed out"}), 504

    except WeatherServiceError:
        return jsonify({"error": "Weather provider unavailable"}), 502
