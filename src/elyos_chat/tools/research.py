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
    # Placeholder. Add quirk handlers here referencing finding IDs (e.g. F-03).
    return body


RESEARCH_TOOL = ToolSpec(
    name="research",
    description="Research a topic in depth. Slow (3-8s).",
    schema=RESEARCH_SCHEMA,
    handler=research_handler,
)
