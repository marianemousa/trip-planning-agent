"""Route a natural-language request to the right tool using Claude."""

import json

import anthropic

from schema import RoutingDecision
from tools import TOOL_REGISTRY

_SYSTEM_PROMPT = """\
You are a routing agent. Analyse the user's request and fill in a routing decision \
that maps it to one of the three tools below.

═══════════════════════════════════════════════════════
AVAILABLE TOOLS
═══════════════════════════════════════════════════════
1. get_weather(location: str, date: str)
   Triggers: weather, forecast, temperature, rain, wind, conditions.
   • location [REQUIRED] — city, district, or named place.
   • date     [REQUIRED] — ISO date (YYYY-MM-DD) or relative ("today", "tomorrow",
                           "next Friday", "this weekend").

2. get_travel_time(origin: str, destination: str, mode: str = "driving")
   Triggers: travel time, commute, how long to get somewhere, drive/walk/transit time.
   • origin      [REQUIRED] — departure place.
   • destination [REQUIRED] — arrival place.
   • mode        [OPTIONAL, default "driving"] — one of "driving", "walking", "transit".

3. convert_currency(amount: float, from_currency: str, to_currency: str)
   Triggers: currency conversion, exchange rate, "how much is X in Y currency".
   • amount        [REQUIRED] — numeric value to convert.
   • from_currency [REQUIRED] — ISO 4217 source code (USD, EUR, GBP, JPY, …).
   • to_currency   [REQUIRED] — ISO 4217 target code.

═══════════════════════════════════════════════════════
AMBIGUITY POLICY — follow exactly, in order
═══════════════════════════════════════════════════════

RULE 1 — Required arg missing with no reasonable default
  → needs_clarification: true
  → Set clarifying_question to the single most useful question that unblocks routing.
  → Leave arguments: {} and tool_called: null.
  → Do NOT guess. Do NOT invent a placeholder value.
  Examples: "What's the weather?" (no location, no date); "Convert 50 dollars" (no target currency).

RULE 1b — Required arg present but clearly invalid
  → Treat the same as missing: needs_clarification: true.
  → Identify the invalid value in the clarifying_question.
  Examples: an unrecognised currency code ("Mars credits"), a nonsensical travel mode ("teleport").
  Do NOT pass an invalid value through to arguments.

RULE 2 — Required arg present but vague, and a sensible default exists
  → Proceed. Resolve the vague value to a concrete one.
  → Log every inference in assumptions_made (e.g. "resolved 'downtown' to city centre",
    "interpreted 'next Tuesday' as 2025-03-18").
  → Set confidence: "medium" unless everything else is clear.
  Examples: "Weather in Paris next Tuesday" → resolve date; "Drive from downtown to the airport" → resolve origin.

RULE 3 — Optional arg missing
  → Use the documented default silently.
  → Do NOT mention it in assumptions_made.
  Example: travel time with no mode → use "driving", say nothing.

RULE 4 — Request maps to no tool
  → tool_called: null, needs_clarification: false.
  → In reasoning: if the question is answerable from general knowledge (e.g. "What is the capital of France?"),
    say so and call it "in-scope general knowledge". If it is completely outside scope
    (e.g. "Write me a poem"), say it is out of scope.

RULE 5 — Request could map to 2 or more tools
  → Pick the single most prominent intent as tool_called.
  → In reasoning, name the secondary tool and explain why you deprioritised it.
  → Set confidence: "medium" or "low" depending on how ambiguous the split is.
  Example: "How long to drive to Rome and what will the weather be like?" → primary: get_travel_time,
           note get_weather as secondary.

═══════════════════════════════════════════════════════
CONFIDENCE CALIBRATION
═══════════════════════════════════════════════════════
• "high"   — intent unambiguous, all args explicit, zero inference.
• "medium" — intent clear, but ≥1 arg was inferred (Rule 2) or a secondary tool exists (Rule 5).
• "low"    — intent or tool match is genuinely uncertain even after applying the rules above.

═══════════════════════════════════════════════════════
RESPONSE FIELD
═══════════════════════════════════════════════════════
Always populate "response" — it is what the user sees:
• needs_clarification=true → copy clarifying_question here verbatim.
• tool_called=null         → write a direct, concise answer (1–2 sentences).
• tool_called=<tool>       → leave as an empty string ""; the framework
                             executes the tool and populates this field.
"""

# Routing decision schema surfaced as a tool so Claude returns structured JSON.
_ROUTE_TOOL: dict = {
    "name": "route_request",
    "description": (
        "Record the routing decision. "
        "Apply the ambiguity policy before filling in each field: "
        "ask when a required arg is truly missing (Rule 1), "
        "infer and log when it is merely vague (Rule 2), "
        "silently default optional args (Rule 3), "
        "null-route out-of-scope requests (Rule 4), "
        "pick a primary tool and note secondary needs (Rule 5)."
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
                "description": (
                    "True only when a REQUIRED arg is missing AND no reasonable default exists "
                    "(Rule 1). False for vague-but-resolvable args (Rule 2) and missing optional args (Rule 3)."
                ),
            },
            "clarifying_question": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "description": (
                    "The single most useful question that unblocks routing. "
                    "Set only when needs_clarification is true; null otherwise."
                ),
            },
            "assumptions_made": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "One entry per inference made under Rule 2 (vague-but-resolvable args). "
                    "Do NOT list Rule 3 optional-arg defaults here."
                ),
            },
            "reasoning": {
                "type": "string",
                "description": "One or two sentences explaining the routing decision.",
            },
            "response": {
                "type": "string",
                "description": (
                    "Text shown directly to the user. "
                    "needs_clarification=true → copy clarifying_question verbatim. "
                    "tool_called=null → write a direct 1–2 sentence answer. "
                    "tool_called=<tool> → leave as empty string ''."
                ),
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
            "response",
        ],
    },
}


# Per-tool parameter specs used by _validate_arguments.
# "kind" is "str" or "num"; "required" controls whether absence triggers clarification.
_ARG_SPECS: dict = {
    "get_weather": [
        {"name": "location", "required": True,  "kind": "str"},
        {"name": "date",     "required": True,  "kind": "str"},
    ],
    "get_travel_time": [
        {"name": "origin",      "required": True,  "kind": "str"},
        {"name": "destination", "required": True,  "kind": "str"},
        {"name": "mode",        "required": False, "kind": "str"},
    ],
    "convert_currency": [
        {"name": "amount",        "required": True, "kind": "num"},
        {"name": "from_currency", "required": True, "kind": "str"},
        {"name": "to_currency",   "required": True, "kind": "str"},
    ],
}


def _validate_arguments(tool: str, args: dict):
    """Check args against _ARG_SPECS.

    Mutates args in place to coerce int→float for numeric params.
    Returns (is_valid, clarifying_question | None).
    """
    for spec in _ARG_SPECS.get(tool, []):
        name = spec["name"]
        value = args.get(name)
        label = name.replace("_", " ")

        missing = value is None or (isinstance(value, str) and not value.strip())
        if missing:
            if spec["required"]:
                return False, (
                    f"I need a {label} to complete this request — could you provide one?"
                )
            continue

        if spec["kind"] == "num":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return False, (
                    f"The {label} should be a number, but I received {value!r}. "
                    "Could you clarify the amount?"
                )
            args[name] = float(value)  # safe coercion: int literals → float
        elif spec["kind"] == "str":
            if not isinstance(value, str):
                return False, (
                    f"Expected {label} to be text, but received a "
                    f"{type(value).__name__} value — could you rephrase?"
                )

    return True, None


def route(request: str) -> RoutingDecision:
    """Route *request* to a tool, execute it, and return a complete RoutingDecision.

    For clarification and direct-answer cases the response is filled by the
    routing model. For tool calls the mock tool is executed and a second
    Claude call generates the natural-language response from the result.
    """
    client = anthropic.Anthropic()

    routing_response = client.messages.create(
        model="claude-opus-5",
        max_tokens=1024,
        thinking={"type": "adaptive"},
        system=_SYSTEM_PROMPT,
        tools=[_ROUTE_TOOL],
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": request}],
    )

    decision = None
    for block in routing_response.content:
        if block.type == "tool_use" and block.name == "route_request":
            inp = block.input
            decision = RoutingDecision(
                tool_called=inp.get("tool_called"),
                arguments=inp.get("arguments") or {},
                confidence=inp["confidence"],
                needs_clarification=inp["needs_clarification"],
                clarifying_question=inp.get("clarifying_question"),
                assumptions_made=inp.get("assumptions_made", []),
                reasoning=inp["reasoning"],
                response=inp.get("response", ""),
            )
            break

    if decision is None:
        raise RuntimeError("Model did not call route_request — unexpected response.")

    # Enforce response == clarifying_question verbatim regardless of what the model wrote.
    if decision.needs_clarification and decision.clarifying_question is not None:
        decision.response = decision.clarifying_question

    # Tool-call path: validate args, execute the mock tool, then generate the natural-language response.
    if decision.tool_called and not decision.needs_clarification:
        valid, question = _validate_arguments(decision.tool_called, decision.arguments)
        if not valid:
            decision.needs_clarification = True
            decision.tool_called = None
            decision.clarifying_question = question
            decision.response = question
            decision.arguments = {}
            return decision

        tool_fn = TOOL_REGISTRY.get(decision.tool_called)
        if tool_fn is None:
            decision.response = f"Unknown tool: {decision.tool_called}"
            return decision

        try:
            tool_result = tool_fn(**decision.arguments)
        except (TypeError, ValueError) as exc:
            decision.response = f"I wasn't able to complete that — {exc}"
            return decision

        summary = client.messages.create(
            model="claude-opus-5",
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"User asked: {request}\n\n"
                        f"Tool: {decision.tool_called}\n"
                        f"Result:\n{json.dumps(tool_result, indent=2)}\n\n"
                        "Write a brief, natural-language answer using the tool result. "
                        "Two or three sentences at most."
                    ),
                }
            ],
        )
        decision.response = next(
            (b.text for b in summary.content if b.type == "text"),
            "The tool ran successfully but I was unable to generate a summary.",
        )

    return decision
