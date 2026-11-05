"""Unit tests for SkyWatch backend HTTP endpoints."""

from unittest.mock import patch

import pytest

from skywatch_backend import create_app
from skywatch_backend.weather import (
    CityNotFoundError,
    WeatherServiceError,
    WeatherTimeoutError,
)


@pytest.fixture
def client():
    """Create an isolated Flask test client."""
    app = create_app()
    app.config.update(TESTING=True)

    with app.test_client() as test_client:
        yield test_client


def test_health_endpoint(client):
    """Liveness endpoint should return HTTP 200."""
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_readiness_endpoint(client):
    """Readiness endpoint should return HTTP 200."""
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ready"}


@patch("skywatch_backend.api.get_weather")
def test_weather_success(mock_get_weather, client):
    """A valid city should return weather data."""

    mock_get_weather.return_value = {
        "city": "London",
        "country": "United Kingdom",
        "temperature": 15.5,
        "temperature_unit": "°C",
        "weather_code": 2,
        "condition": "Partly cloudy",
    }

    response = client.get("/api/weather?city=London")

    assert response.status_code == 200
    assert response.get_json()["city"] == "London"
    assert response.get_json()["temperature"] == 15.5

    mock_get_weather.assert_called_once_with("London")


def test_weather_missing_city(client):
    """Missing city should return HTTP 400."""
    response = client.get("/api/weather")

    assert response.status_code == 400
    assert response.get_json()["error"] == ("City parameter is required")


def test_weather_whitespace_city(client):
    """Whitespace-only city should return HTTP 400."""
    response = client.get("/api/weather?city=%20%20")

    assert response.status_code == 400


def test_weather_city_too_long(client):
    """City names exceeding the limit should be rejected."""
    city = "A" * 101

    response = client.get(
        "/api/weather",
        query_string={"city": city},
    )

    assert response.status_code == 400


@patch("skywatch_backend.api.get_weather")
def test_weather_city_not_found(mock_get_weather, client):
    """Unknown cities should return HTTP 404."""

    mock_get_weather.side_effect = CityNotFoundError()

    response = client.get("/api/weather?city=UnknownCity")

    assert response.status_code == 404
    assert response.get_json()["error"] == "City not found"


@patch("skywatch_backend.api.get_weather")
def test_weather_timeout(mock_get_weather, client):
    """Upstream timeouts should return HTTP 504."""

    mock_get_weather.side_effect = WeatherTimeoutError()

    response = client.get("/api/weather?city=London")

    assert response.status_code == 504
    assert response.get_json()["error"] == ("Weather provider timed out")


@patch("skywatch_backend.api.get_weather")
def test_weather_provider_failure(mock_get_weather, client):
    """Upstream failures should return HTTP 502."""

    mock_get_weather.side_effect = WeatherServiceError()

    response = client.get("/api/weather?city=London")

    assert response.status_code == 502
    assert response.get_json()["error"] == ("Weather provider unavailable")
