"""Tests for the SkyWatch frontend."""

from unittest.mock import Mock, patch

import pytest
import requests

from skywatch_frontend import create_app


@pytest.fixture
def client():
    """Create a Flask test client."""
    app = create_app()
    app.config["TESTING"] = True

    return app.test_client()


def test_health(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_home_page(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"SkyWatch" in response.data


@patch("skywatch_frontend.routes.requests.get")
def test_weather_success(mock_get, client):
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "city": "London",
        "country": "United Kingdom",
        "temperature": 12.5,
        "temperature_unit": "°C",
        "condition": "Cloudy",
    }
    mock_get.return_value = mock_response

    response = client.get("/?city=London")

    assert response.status_code == 200
    assert b"London" in response.data
    assert b"12.5" in response.data
    assert b"Cloudy" in response.data
    mock_get.assert_called_once()


@patch("skywatch_frontend.routes.requests.get")
def test_city_not_found(mock_get, client):
    mock_response = Mock()
    mock_response.status_code = 404
    mock_get.return_value = mock_response

    response = client.get("/?city=UnknownCity")

    assert response.status_code == 200
    assert b"City not found" in response.data


@patch("skywatch_frontend.routes.requests.get")
def test_backend_timeout(mock_get, client):
    mock_get.side_effect = requests.Timeout()

    response = client.get("/?city=London")

    assert response.status_code == 200
    assert b"timed out" in response.data


@patch("skywatch_frontend.routes.requests.get")
def test_backend_connection_error(mock_get, client):
    mock_get.side_effect = requests.ConnectionError()

    response = client.get("/?city=London")

    assert response.status_code == 200
    assert b"Unable to retrieve weather information" in response.data


@patch("skywatch_frontend.routes.requests.get")
def test_backend_unavailable(mock_get, client):
    mock_response = Mock()
    mock_response.status_code = 502
    mock_get.return_value = mock_response

    response = client.get("/?city=London")

    assert response.status_code == 200
    assert b"temporarily unavailable" in response.data


@patch("skywatch_frontend.routes.requests.get")
def test_empty_city_does_not_call_backend(mock_get, client):
    response = client.get("/?city=%20%20%20")

    assert response.status_code == 200
    mock_get.assert_not_called()


@patch("skywatch_frontend.routes.requests.get")
def test_city_is_sent_as_query_parameter(mock_get, client):
    mock_response = Mock()
    mock_response.status_code = 404
    mock_get.return_value = mock_response

    client.get("/?city=New%20York")

    args, kwargs = mock_get.call_args

    assert args[0].endswith("/api/weather")
    assert kwargs["params"] == {"city": "New York"}
    assert kwargs["timeout"] == (3, 7)
