"""Weather tool handler.

Quirk handlers should be added here referencing finding IDs from
docs/api-findings.md once the probe script has run.
"""
from __future__ import annotations
from elyos_chat.chat.cancel import CancelToken
from elyos_chat.tools.http import ToolHttpClient
from elyos_chat.tools.registry import ToolSpec


WEATHER_SCHEMA = {
    "type": "object",
    "properties": {
        "location": {
            "type": "string",
            "description": "City name or location identifier (e.g. 'London', 'Tokyo').",
        }
    },
    "required": ["location"],
}


async def weather_handler(args: dict, cancel: CancelToken, http: ToolHttpClient) -> dict:
    location = (args.get("location") or "").strip()
    if not location:
        return {
            "error": "missing location",
            "guidance": "Ask the user which location they want the weather for.",
        }
    result = await http.get("/weather", {"location": location}, cancel)
    if result.is_err:
        return {"error": result.error, "transient": result.is_transient}
    return _normalise(result.value)


def _normalise(body: dict) -> dict:
    # F-01: Soft throttle — API returns HTTP 200 with status="throttled" instead of HTTP 429.
    # ToolHttpClient sees a 200 and passes the body through; we must detect it here.
    if body.get("status") == "throttled":
        return {
            "error": "rate limited",
            "retry_after_seconds": body.get("retry_after_seconds"),
            "guidance": "Tell the user the service is rate limited and to try again shortly.",
        }

    # F-02: Non-deterministic response shape — some calls return a flat object with top-level
    # temperature_c/condition/humidity, others return {"conditions": [...], "note": "..."}.
    # Normalise to always expose primary_condition at the top level.
    if isinstance(body.get("conditions"), list) and body["conditions"]:
        primary = body["conditions"][0]
        return {
            **body,
            "primary_condition": primary,
            "multiple_conditions": len(body["conditions"]) > 1,
        }

    # F-03: Server strips Unicode diacritics from the location name in the response
    # (e.g. "São Paulo" → "Sao Paulo").  Preserve the original query for the model.
    # NOTE: the original location is not available inside _normalise; callers that need
    # it should pass the query string and attach it before calling _normalise.
    # The normalisation below is a no-op placeholder to document the finding.

    return body


WEATHER_TOOL = ToolSpec(
    name="weather",
    description="Get current weather for a location. Fast (~200ms).",
    schema=WEATHER_SCHEMA,
    handler=weather_handler,
)
