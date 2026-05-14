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
    return _normalise(result.value, location_query=location)


def _normalise(body: dict, location_query: str | None = None) -> dict:
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
    # Flatten so the model always sees one consistent shape; drop the original conditions
    # array after promoting primary to the top level.
    if isinstance(body.get("conditions"), list) and body["conditions"]:
        primary = body["conditions"][0]
        rest = {k: v for k, v in body.items() if k != "conditions"}
        body = {**rest, **primary,
                "multiple_conditions": len(body["conditions"]) > 1,
                "all_conditions": body["conditions"] if len(body["conditions"]) > 1 else None}
        # Drop None values so the model doesn't see all_conditions: null when there's only one.
        body = {k: v for k, v in body.items() if v is not None}

    # F-03: Server strips Unicode diacritics from the location name in the response
    # (e.g. "São Paulo" → "Sao Paulo").  Attach the original query so the LLM can
    # disambiguate between the server-normalized and user-supplied forms.
    if location_query is not None:
        body = {**body, "location_query": location_query}

    return body


WEATHER_TOOL = ToolSpec(
    name="weather",
    description="Get current weather for a location. Fast (~200ms).",
    schema=WEATHER_SCHEMA,
    handler=weather_handler,
)
