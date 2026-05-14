"""Unit tests for weather and research tool normalisation handlers."""
from __future__ import annotations


def test_weather_normalise_handles_throttle():
    from elyos_chat.tools.weather import _normalise
    body = {"status": "throttled", "message": "Rate limit exceeded. Please wait.",
            "retry_after_seconds": 27, "data": None}
    result = _normalise(body)
    assert result.get("error") == "rate limited"
    assert result.get("retry_after_seconds") == 27


def test_weather_normalise_flattens_multi_conditions():
    from elyos_chat.tools.weather import _normalise
    body = {"location": "London", "conditions": [
        {"temperature_c": 10, "condition": "rain"},
        {"temperature_c": 12, "condition": "cloudy"},
    ], "note": "Multiple conditions reported"}
    result = _normalise(body)
    assert result["temperature_c"] == 10
    assert result["condition"] == "rain"
    assert result["multiple_conditions"] is True
    assert "conditions" not in result


def test_research_normalise_handles_throttle():
    from elyos_chat.tools.research import _normalise
    body = {"status": "throttled", "retry_after_seconds": 30, "data": None}
    result = _normalise(body)
    assert result.get("error") == "rate limited"
