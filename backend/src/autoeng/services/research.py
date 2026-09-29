"""Research assistant (spec §23): web search for material properties and part specifications.

The assistant finds and extracts; the user decides. Every value comes back as a
*candidate* with its source URL, a verbatim quote and a confidence level. Nothing
enters the material library until the user reviews and accepts it, and accepted
values keep their citation, so the trust layer can always show where a number
came from. Source URLs are cross-checked against the pages the search actually
returned, so a cited URL the model did not really see is flagged.
"""

from __future__ import annotations

import json
import logging

import anthropic

from autoeng.domain.materials import PROPERTY_UNITS
from autoeng.settings import get_settings

log = logging.getLogger(__name__)

MAX_CONTINUATIONS = 5
KINDS = ("material", "part")

SYSTEM = """You are an engineering research assistant for an automotive engineering platform.
Search the web for documented technical data and report exactly what the sources say.

Rules:
- Prefer primary sources: manufacturer datasheets, standards bodies, handbooks, peer-reviewed papers.
- Report only values a source states. Never estimate, interpolate or fill gaps from memory.
  If you cannot find a value, leave it out and say so in caveats.
- Every value needs the URL of the page it came from and a short verbatim quote containing it.
- Record the condition the value applies to (heat treatment, temper, temperature, test standard, cycles).
- When sources disagree, report each value separately rather than averaging.
- Convert units only when unambiguous, and say so in notes.
- For materials, use these property keys where they apply: {keys}. Use other short snake_case keys otherwise."""

PROPERTY_SCHEMA = {
    "type": "object",
    "properties": {
        "key": {"type": "string"},
        "label": {"type": "string"},
        "value": {"type": "number"},
        "unit": {"type": "string"},
        "value_min": {"type": ["number", "null"]},
        "value_max": {"type": ["number", "null"]},
        "condition": {"type": "string"},
        "source_kind": {"type": "string", "enum": ["manufacturer", "literature", "unknown"]},
        "source_title": {"type": "string"},
        "source_url": {"type": "string"},
        "quote": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "notes": {"type": "string"},
    },
    "required": ["key", "label", "value", "unit", "value_min", "value_max", "condition", "source_kind",
                 "source_title", "source_url", "quote", "confidence", "notes"],
    "additionalProperties": False,
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "category": {"type": "string"},
                    "condition": {"type": "string"},
                    "properties": {"type": "array", "items": PROPERTY_SCHEMA},
                },
                "required": ["name", "category", "condition", "properties"],
                "additionalProperties": False,
            },
        },
        "caveats": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "items", "caveats"],
    "additionalProperties": False,
}


class ResearchUnavailable(RuntimeError):
    pass


def available() -> bool:
    return bool(get_settings().research_api_key)


def _prompt(kind: str, query: str) -> str:
    if kind == "material":
        return (f"Find documented engineering properties for this material: {query}\n"
                "Include mechanical, thermal and fatigue properties where sources state them.")
    return (f"Find documented technical specifications for this automotive part: {query}\n"
            "Include ratings and limits (e.g. torque capacity, flow, pressure, temperature, speed), "
            "dimensions and materials, as stated by the manufacturer or reputable sources.")


def run(kind: str, query: str) -> dict:
    """Search and extract. Blocking; call from a background thread."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    settings = get_settings()
    if not settings.research_api_key:
        raise ResearchUnavailable("The research assistant is not configured (set AUTOENG_RESEARCH_API_KEY)")
    client = anthropic.Anthropic(api_key=settings.research_api_key)

    messages: list[dict] = [{"role": "user", "content": _prompt(kind, query)}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}]
    seen_urls: set[str] = set()
    response = None
    for _ in range(MAX_CONTINUATIONS + 1):
        response = client.beta.messages.create(
            model=settings.research_model,
            max_tokens=16000,
            system=SYSTEM.format(keys=", ".join(PROPERTY_UNITS)),
            messages=messages,
            tools=tools,
            output_config={"effort": "high", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        for block in response.content:
            if block.type == "web_search_tool_result" and isinstance(block.content, list):
                seen_urls.update(r.url for r in block.content if getattr(r, "url", None))
        if response.stop_reason != "pause_turn":
            break
        # Server-side tool loop paused: send the partial turn back and let it resume.
        messages = [messages[0], {"role": "assistant", "content": response.content}]

    if response is None or response.stop_reason == "refusal":
        raise RuntimeError("The research request was declined")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("The research answer was too long; narrow the query")
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise RuntimeError(f"No answer returned (stop reason: {response.stop_reason})")
    data = json.loads(text)

    for item in data["items"]:
        for prop in item["properties"]:
            prop["url_verified"] = prop["source_url"] in seen_urls
    data["searched_urls"] = sorted(seen_urls)
    data["model"] = response.model
    data["notice"] = ("Machine-extracted candidates. Check each value against its source before accepting it; "
                      "accepted values keep their citation and are never marked as verified test data.")
    return data
