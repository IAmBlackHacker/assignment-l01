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
    # Placeholder. Add quirk handlers here referencing finding IDs (e.g. F-01).
    return body


WEATHER_TOOL = ToolSpec(
    name="weather",
    description="Get current weather for a location. Fast (~200ms).",
    schema=WEATHER_SCHEMA,
    handler=weather_handler,
)
