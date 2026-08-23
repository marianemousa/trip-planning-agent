"""Route a natural-language request to the right tool using Claude."""

import anthropic
from schema import RoutingDecision

_SYSTEM_PROMPT = """\
You are a routing agent. Given a user's natural-language request, decide which of \
these three tools to call, extract the arguments, and fill in the routing decision.

Available tools:
1. get_weather(location: str, date: str)
   - Use for weather, forecast, temperature, rain, conditions at a place and time.
   - location: city or place name
   - date: ISO date (YYYY-MM-DD) or relative like "today", "tomorrow", "next Friday"

2. get_travel_time(origin: str, destination: str, mode: str = "driving")
   - Use for trip duration, commute time, how long to get somewhere.
   - mode: one of "driving", "walking", "transit" — default "driving" if unspecified.

3. convert_currency(amount: float, from_currency: str, to_currency: str)
   - Use for currency conversion, exchange rates, "how much is X in Y".
   - Currencies as ISO 4217 codes (USD, EUR, GBP, JPY, …).

Rules for the decision:
- Set needs_clarification=true when required parameters are genuinely ambiguous or missing
  and you cannot make a reasonable assumption (e.g. no location at all for weather).
- Set confidence="high" when intent and args are crystal-clear.
- Set confidence="medium" when you inferred something but it's a reasonable guess.
- Set confidence="low" when the request could plausibly match multiple tools or is vague.
- assumptions_made lists every inference you made (can be empty).
- If tool_called is null, still fill in reasoning explaining why no tool matched.
"""

# Routing decision schema surfaced as a tool so Claude returns structured JSON.
_ROUTE_TOOL: dict = {
    "name": "route_request",
    "description": (
        "Record the routing decision: which tool to call, with what arguments, "
        "and metadata about confidence and assumptions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tool_called": {
                "anyOf": [
                    {
                        "type": "string",
                        "enum": ["get_weather", "get_travel_time", "convert_currency"],
                    },
                    {"type": "null"},
                ],
                "description": "Tool to invoke, or null if no tool matches.",
            },
            "arguments": {
                "type": "object",
                "description": "Arguments to pass to tool_called. Empty object if null.",
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
            },
            "needs_clarification": {
                "type": "boolean",
                "description": "True when the request is too ambiguous to route confidently.",
            },
            "clarifying_question": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "description": "Question to resolve ambiguity, or null.",
            },
            "assumptions_made": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Every inference or default applied when interpreting the request.",
            },
            "reasoning": {
                "type": "string",
                "description": "One or two sentences explaining the routing decision.",
            },
        },
        "required": [
            "tool_called",
            "arguments",
            "confidence",
            "needs_clarification",
            "clarifying_question",
            "assumptions_made",
            "reasoning",
        ],
    },
}


def route(request: str) -> RoutingDecision:
    """Send *request* to Claude and return a structured RoutingDecision."""
    client = anthropic.Anthropic()

    response = client.messages.create(
        model="claude-opus-5",
        max_tokens=1024,
        thinking={"type": "adaptive"},
        system=_SYSTEM_PROMPT,
        tools=[_ROUTE_TOOL],
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": request}],
    )

    # The model is forced to call route_request — find that block.
    for block in response.content:
        if block.type == "tool_use" and block.name == "route_request":
            inp = block.input
            return RoutingDecision(
                tool_called=inp.get("tool_called"),
                arguments=inp.get("arguments", {}),
                confidence=inp["confidence"],
                needs_clarification=inp["needs_clarification"],
                clarifying_question=inp.get("clarifying_question"),
                assumptions_made=inp.get("assumptions_made", []),
                reasoning=inp["reasoning"],
            )

    raise RuntimeError("Model did not call route_request — unexpected response.")
