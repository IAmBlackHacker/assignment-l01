"""Research tool handler.

Quirk handlers should be added here referencing finding IDs from
docs/api-findings.md once the probe script has run.
"""
from __future__ import annotations
from elyos_chat.chat.cancel import CancelToken
from elyos_chat.tools.http import ToolHttpClient
from elyos_chat.tools.registry import ToolSpec


RESEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {
            "type": "string",
            "description": "Topic to research (e.g. 'solar energy', 'CRISPR gene editing').",
        }
    },
    "required": ["topic"],
}


async def research_handler(args: dict, cancel: CancelToken, http: ToolHttpClient) -> dict:
    topic = (args.get("topic") or "").strip()
    if not topic:
        return {
            "error": "missing topic",
            "guidance": "Ask the user what topic to research.",
        }
    result = await http.get("/research", {"topic": topic}, cancel)
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

    # F-07: Stale-cache responses — for obscure or empty topics the API returns
    # cached data that may be many months old, signalled by "cached": true in the body.
    # Surface a staleness_warning so the model can caveat its response.
    if body.get("cached") is True:
        import math
        age_s = body.get("cache_age_seconds")
        age_days = math.floor(age_s / 86400) if isinstance(age_s, (int, float)) else None
        body = {
            **body,
            "staleness_warning": (
                f"This summary is from a cache that is approximately {age_days} days old "
                "and may not reflect recent developments."
            ) if age_days is not None else (
                "This summary is cached and may not reflect recent developments."
            ),
        }

    # F-08: generated_at is non-deterministic across identical requests (timestamp changes
    # each call even when summary text is identical).  Rename to response_timestamp to
    # signal it is metadata rather than a stable content identifier.
    if "generated_at" in body:
        body = {k: v for k, v in body.items() if k != "generated_at"} | {
            "response_timestamp": body["generated_at"]
        }

    return body


RESEARCH_TOOL = ToolSpec(
    name="research",
    description="Research a topic in depth. Slow (3-8s).",
    schema=RESEARCH_SCHEMA,
    handler=research_handler,
)
