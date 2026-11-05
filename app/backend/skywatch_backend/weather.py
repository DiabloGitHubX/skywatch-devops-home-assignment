"""Open-Meteo weather API integration."""

import math

import requests

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Connection timeout: 3 seconds; read timeout: 7 seconds.
REQUEST_TIMEOUT = (3, 7)

WEATHER_CONDITIONS = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


class CityNotFoundError(Exception):
    """Raised when a city cannot be resolved."""


class WeatherServiceError(Exception):
    """Raised when the upstream weather service fails."""


class WeatherTimeoutError(WeatherServiceError):
    """Raised when an upstream request times out."""


def _parse_json_object(response: requests.Response) -> dict:
    """Decode an upstream response and require a JSON object."""
    try:
        data = response.json()
    except ValueError as exc:
        raise WeatherServiceError("Invalid JSON from weather provider") from exc

    if not isinstance(data, dict):
        raise WeatherServiceError("Unexpected response format from weather provider")

    return data


def get_weather(city: str) -> dict:
    """Retrieve current weather for a city using Open-Meteo."""

    try:
        # Step 1: Resolve the city into geographic coordinates.
        location_response = requests.get(
            GEOCODING_URL,
            params={
                "name": city,
                "count": 1,
                "language": "en",
                "format": "json",
            },
            timeout=REQUEST_TIMEOUT,
        )
        location_response.raise_for_status()

        location_data = _parse_json_object(location_response)
        locations = location_data.get("results")

        if locations is None or locations == []:
            raise CityNotFoundError(f"No location found for '{city}'")

        if not isinstance(locations, list):
            raise WeatherServiceError("Invalid geocoding results")

        location = locations[0]

        if not isinstance(location, dict):
            raise WeatherServiceError("Invalid location data")

        latitude = location["latitude"]
        longitude = location["longitude"]
        location_name = location["name"]
        country = location.get("country", "Unknown")

        if (
            isinstance(latitude, bool)
            or not isinstance(latitude, (int, float))
            or not math.isfinite(latitude)
            or not -90 <= latitude <= 90
            or isinstance(longitude, bool)
            or not isinstance(longitude, (int, float))
            or not math.isfinite(longitude)
            or not -180 <= longitude <= 180
            or not isinstance(location_name, str)
            or not location_name.strip()
            or not isinstance(country, str)
        ):
            raise WeatherServiceError("Invalid location fields")

        # Step 2: Retrieve current weather for the coordinates.
        weather_response = requests.get(
            FORECAST_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": "temperature_2m,weather_code",
                "timezone": "auto",
            },
            timeout=REQUEST_TIMEOUT,
        )
        weather_response.raise_for_status()

        weather_data = _parse_json_object(weather_response)

        current = weather_data["current"]
        current_units = weather_data.get("current_units", {})

        if not isinstance(current, dict):
            raise WeatherServiceError("Invalid current weather data")

        if not isinstance(current_units, dict):
            raise WeatherServiceError("Invalid weather units")

        temperature = current["temperature_2m"]
        weather_code = current["weather_code"]
        temperature_unit = current_units.get("temperature_2m", "°C")

        if (
            isinstance(temperature, bool)
            or not isinstance(temperature, (int, float))
            or not math.isfinite(temperature)
            or type(weather_code) is not int
            or not isinstance(temperature_unit, str)
            or not temperature_unit
        ):
            raise WeatherServiceError("Invalid weather fields")

        # Step 3: Return a consistent response to the Flask API.
        return {
            "city": location_name,
            "country": country,
            "temperature": temperature,
            "temperature_unit": temperature_unit,
            "weather_code": weather_code,
            "condition": WEATHER_CONDITIONS.get(weather_code, "Unknown"),
        }

    except requests.Timeout as exc:
        raise WeatherTimeoutError("Weather provider request timed out") from exc

    except requests.RequestException as exc:
        raise WeatherServiceError("Weather provider is unavailable") from exc

    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise WeatherServiceError("Invalid response from weather provider") from exc
