# Trip-Planning Agent

Hi Samir, Mariam, and Sona!

This is my submission for the agentic assistant exercise. Below is a quick overview of what was built and how it maps to what you asked for.

## What we built

A small agent that takes a natural-language request and routes it to one of three mock tools:

- **`get_weather(location, date)`** — weather forecast for a place and date
- **`get_travel_time(origin, destination, mode)`** — estimated travel time between two places
- **`convert_currency(amount, from_currency, to_currency)`** — currency conversion

The routing decision is made by a model, which is prompted to follow an explicit ambiguity policy and always return a structured decision object, which either triggers a mock tool call or is handled directly (a clarifying question or a direct answer), depending on the case.

## How this maps to the prompt

**Defining the tools** — each tool has a clear name, a description of when to use it, and explicit required vs. optional parameters (see the tool definitions in `agent.py` and their mock implementations in `tools.py`). 

**Handling ambiguous or uncertain input** — the agent follows five explicit rules, in priority order:
1. Required arg missing, no reasonable default → ask a clarifying question
2. Required arg present but invalid (e.g. a made-up currency code) → treated the same as missing, ask
3. Required arg vague but resolvable (e.g. "next Tuesday") → proceed, but log the assumption made
4. Optional arg missing → use a sensible default silently
5. Request maps to no tool, or to more than one → route accordingly and say why in the reasoning

Argument values are also validated against each tool's expected types before execution, so a malformed or wrong-typed value gets caught and turned into a clarifying question rather than silently passed through or crashing.

**Structuring the output** — every request returns the same shape, whether or not a tool was called:

```json
{
  "tool_called": "string or null",
  "arguments": {},
  "confidence": "high | medium | low",
  "needs_clarification": true,
  "clarifying_question": "string or null",
  "assumptions_made": ["string"],
  "reasoning": "string",
  "response": "string, what the end user actually sees"
}
```

Every field is always present, even when null — the goal was something a downstream system could parse reliably without needing to handle disappearing keys.

## Repo structure

- `agent.py` — routing logic, ambiguity policy, argument validation
- `tools.py` — the three mock tools
- `schema.py` — the structured output shape
- `main.py` — CLI entry point 
- `test_tools.py` — unit tests on the tools themselves, in isolation
- `test_routing.py` — eval-style tests on routing/ambiguity behavior (requires a live `ANTHROPIC_API_KEY` to run)

## Scope notes

Given the 60-minute framing, a few things were intentionally left out. Details are in my submission email, but briefly: this wasn't tested end-to-end locally (would have required setting up a dedicated API key + frontend for testing), and a sub-agent review pass was run but its recommendations weren't applied. If this were headed to production, I'd apply the sub-agent recommendations, add a proper frontend, broaden test coverage with integration tests, define evals, and wire up observability via LangSmith.

Looking forward to discussing!
