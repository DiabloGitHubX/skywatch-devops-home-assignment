"""Unit tests for the Open-Meteo weather client."""

from unittest.mock import Mock, patch

import pytest
import requests
from skywatch_backend.weather import (
    CityNotFoundError,
    WeatherServiceError,
    WeatherTimeoutError,
    get_weather,
)


def mock_response(payload, status_code=200):
    """Create a simulated HTTP response."""
    response = Mock()
    response.status_code = status_code
    response.json.return_value = payload

    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(
            "Upstream HTTP error"
        )

    return response


@pytest.fixture
def location_payload():
    return {
        "results": [
            {
                "name": "London",
                "country": "United Kingdom",
                "latitude": 51.5085,
                "longitude": -0.1257,
            }
        ]
    }


@pytest.fixture
def forecast_payload():
    return {
        "current": {
            "temperature_2m": 15.5,
            "weather_code": 3,
        },
        "current_units": {
            "temperature_2m": "°C",
        },
    }


@patch("skywatch_backend.weather.requests.get")
def test_get_weather_success(mock_get, location_payload, forecast_payload):
    """Valid provider responses should produce weather data."""
    mock_get.side_effect = [
        mock_response(location_payload),
        mock_response(forecast_payload),
    ]

    result = get_weather("London")

    assert result["city"] == "London"
    assert result["country"] == "United Kingdom"
    assert result["temperature"] == 15.5
    assert result["condition"] == "Overcast"
    assert result["weather_code"] == 3
    assert mock_get.call_count == 2


@patch("skywatch_backend.weather.requests.get")
def test_city_not_found(mock_get):
    """No geocoding matches should raise CityNotFoundError."""
    mock_get.return_value = mock_response({})

    with pytest.raises(CityNotFoundError):
        get_weather("UnknownCity")

    mock_get.assert_called_once()


@patch("skywatch_backend.weather.requests.get")
def test_upstream_timeout(mock_get):
    """A provider timeout should raise WeatherTimeoutError."""
    mock_get.side_effect = requests.Timeout("Timed out")

    with pytest.raises(WeatherTimeoutError):
        get_weather("London")


@patch("skywatch_backend.weather.requests.get")
def test_upstream_http_error(mock_get):
    """HTTP failures should raise WeatherServiceError."""
    mock_get.return_value = mock_response({}, status_code=503)

    with pytest.raises(WeatherServiceError):
        get_weather("London")


@patch("skywatch_backend.weather.requests.get")
def test_malformed_json(mock_get):
    """Invalid JSON should raise WeatherServiceError."""
    response = mock_response({})
    response.json.side_effect = ValueError("Invalid JSON")
    mock_get.return_value = response

    with pytest.raises(WeatherServiceError):
        get_weather("London")


@patch("skywatch_backend.weather.requests.get")
def test_invalid_coordinates(mock_get):
    """Out-of-range coordinates should be rejected."""
    mock_get.return_value = mock_response(
        {
            "results": [
                {
                    "name": "London",
                    "country": "United Kingdom",
                    "latitude": 999,
                    "longitude": -0.1257,
                }
            ]
        }
    )

    with pytest.raises(WeatherServiceError):
        get_weather("London")


@patch("skywatch_backend.weather.requests.get")
def test_missing_forecast_fields(mock_get, location_payload):
    """Missing required forecast fields should be rejected."""
    mock_get.side_effect = [
        mock_response(location_payload),
        mock_response({"current": {}}),
    ]

    with pytest.raises(WeatherServiceError):
        get_weather("London")


@patch("skywatch_backend.weather.requests.get")
def test_invalid_temperature(mock_get, location_payload, forecast_payload):
    """Non-numeric temperatures should be rejected."""
    forecast_payload["current"]["temperature_2m"] = "hot"

    mock_get.side_effect = [
        mock_response(location_payload),
        mock_response(forecast_payload),
    ]

    with pytest.raises(WeatherServiceError):
        get_weather("London")


@patch("skywatch_backend.weather.requests.get")
def test_unknown_weather_code(mock_get, location_payload, forecast_payload):
    """Unknown weather codes should have a safe fallback."""
    forecast_payload["current"]["weather_code"] = 999

    mock_get.side_effect = [
        mock_response(location_payload),
        mock_response(forecast_payload),
    ]

    result = get_weather("London")

    assert result["condition"] == "Unknown"
    assert result["weather_code"] == 999
