"""
Unit tests for the routing agent.

All Anthropic API calls are mocked. Each test defines the *ideal* model
response for a given input, then asserts that agent.route() parses it into
the correct RoutingDecision.
"""

import unittest
from unittest.mock import MagicMock, patch

from agent import route


# ── Mock helper ───────────────────────────────────────────────────────────────

def _mock_decision(
    tool_called,
    arguments,
    confidence,
    needs_clarification,
    clarifying_question,
    assumptions_made,
    reasoning,
):
    """Return a fake Anthropic response containing a route_request tool call."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = "route_request"
    block.input = {
        "tool_called": tool_called,
        "arguments": arguments,
        "confidence": confidence,
        "needs_clarification": needs_clarification,
        "clarifying_question": clarifying_question,
        "assumptions_made": assumptions_made,
        "reasoning": reasoning,
    }
    response = MagicMock()
    response.content = [block]
    return response


def _patch(response):
    """Patch agent.anthropic.Anthropic so messages.create returns *response*."""
    patcher = patch("agent.anthropic.Anthropic")
    mock_class = patcher.start()
    mock_class.return_value.messages.create.return_value = response
    return patcher


# ── Test cases ────────────────────────────────────────────────────────────────

class TestRouting(unittest.TestCase):

    # 1 ── clear single tool: get_weather ─────────────────────────────────────

    def test_01_clear_weather(self):
        p = _patch(_mock_decision(
            tool_called="get_weather",
            arguments={"location": "London", "date": "2025-09-01"},
            confidence="high",
            needs_clarification=False,
            clarifying_question=None,
            assumptions_made=[],
            reasoning="Location and date are explicit; routing to get_weather.",
        ))
        try:
            d = route("What's the weather in London on 2025-09-01?")
            self.assertEqual(d.tool_called, "get_weather")
            self.assertEqual(d.arguments["location"], "London")
            self.assertEqual(d.arguments["date"], "2025-09-01")
            self.assertEqual(d.confidence, "high")
            self.assertFalse(d.needs_clarification)
            self.assertIsNone(d.clarifying_question)
            self.assertEqual(d.assumptions_made, [])
        finally:
            p.stop()

    # 2 ── clear single tool: get_travel_time ─────────────────────────────────

    def test_02_clear_travel_time(self):
        p = _patch(_mock_decision(
            tool_called="get_travel_time",
            arguments={"origin": "Berlin", "destination": "Munich", "mode": "driving"},
            confidence="high",
            needs_clarification=False,
            clarifying_question=None,
            assumptions_made=[],
            reasoning="Origin, destination, and mode are all explicit.",
        ))
        try:
            d = route("How long does it take to drive from Berlin to Munich?")
            self.assertEqual(d.tool_called, "get_travel_time")
            self.assertEqual(d.arguments["origin"], "Berlin")
            self.assertEqual(d.arguments["destination"], "Munich")
            self.assertEqual(d.arguments["mode"], "driving")
            self.assertEqual(d.confidence, "high")
            self.assertFalse(d.needs_clarification)
        finally:
            p.stop()

    # 3 ── clear single tool: convert_currency ────────────────────────────────

    def test_03_clear_currency(self):
        p = _patch(_mock_decision(
            tool_called="convert_currency",
            arguments={"amount": 250.0, "from_currency": "USD", "to_currency": "JPY"},
            confidence="high",
            needs_clarification=False,
            clarifying_question=None,
            assumptions_made=[],
            reasoning="Amount and both currency codes are explicit.",
        ))
        try:
            d = route("Convert 250 USD to JPY.")
            self.assertEqual(d.tool_called, "convert_currency")
            self.assertEqual(d.arguments["amount"], 250.0)
            self.assertEqual(d.arguments["from_currency"], "USD")
            self.assertEqual(d.arguments["to_currency"], "JPY")
            self.assertEqual(d.confidence, "high")
            self.assertFalse(d.needs_clarification)
            self.assertEqual(d.assumptions_made, [])
        finally:
            p.stop()

    # 4 ── no tool needed: in-scope general knowledge ─────────────────────────

    def test_04_no_tool_general_knowledge(self):
        p = _patch(_mock_decision(
            tool_called=None,
            arguments={},
            confidence="high",
            needs_clarification=False,
            clarifying_question=None,
            assumptions_made=[],
            reasoning=(
                "Japan's currency is the Japanese Yen (JPY). "
                "This is in-scope general knowledge; no tool required."
            ),
        ))
        try:
            d = route("What currency does Japan use?")
            self.assertIsNone(d.tool_called)
            self.assertEqual(d.arguments, {})
            self.assertFalse(d.needs_clarification)
            self.assertIsNone(d.clarifying_question)
            self.assertIn("in-scope general knowledge", d.reasoning.lower())
        finally:
            p.stop()

    # 5 ── missing required arg: no location for weather ──────────────────────

    def test_05_missing_location(self):
        p = _patch(_mock_decision(
            tool_called=None,
            arguments={},
            confidence="low",
            needs_clarification=True,
            clarifying_question="Which city or location would you like the weather for?",
            assumptions_made=[],
            reasoning="Rule 1: location is required for get_weather but was not provided.",
        ))
        try:
            d = route("What's the weather going to be like tomorrow?")
            self.assertTrue(d.needs_clarification)
            self.assertIsNotNone(d.clarifying_question)
            self.assertIsNone(d.tool_called)
            self.assertEqual(d.arguments, {})
        finally:
            p.stop()

    # 6 ── missing required arg: no target currency ───────────────────────────

    def test_06_missing_target_currency(self):
        p = _patch(_mock_decision(
            tool_called=None,
            arguments={},
            confidence="low",
            needs_clarification=True,
            clarifying_question="What currency would you like to convert 80 euros into?",
            assumptions_made=[],
            reasoning="Rule 1: to_currency is required for convert_currency but was not provided.",
        ))
        try:
            d = route("How much is 80 euros worth?")
            self.assertTrue(d.needs_clarification)
            self.assertIsNotNone(d.clarifying_question)
            self.assertIsNone(d.tool_called)
        finally:
            p.stop()

    # 7 ── vague but resolvable: "the city" is irresolvable → ask ─────────────
    # "next Tuesday" is resolvable, but "the city" has no referent — Rule 1.

    def test_07_irresolvable_location(self):
        p = _patch(_mock_decision(
            tool_called=None,
            arguments={},
            confidence="low",
            needs_clarification=True,
            clarifying_question="Which city are you asking about?",
            assumptions_made=[],
            reasoning=(
                "Rule 1: 'the city' has no referent in context and cannot be resolved "
                "to a specific location. Asking for clarification."
            ),
        ))
        try:
            d = route("Will it rain in the city next Tuesday?")
            self.assertTrue(d.needs_clarification)
            self.assertIsNotNone(d.clarifying_question)
            self.assertIsNone(d.tool_called)
        finally:
            p.stop()

    # 8 ── vague but resolvable: mode omitted → silent default (Rule 3) ────────

    def test_08_optional_mode_defaulted(self):
        p = _patch(_mock_decision(
            tool_called="get_travel_time",
            arguments={
                "origin": "downtown Chicago",
                "destination": "O'Hare",
                "mode": "driving",
            },
            confidence="high",
            needs_clarification=False,
            clarifying_question=None,
            # mode is optional — Rule 3 says do NOT log it in assumptions_made
            assumptions_made=[],
            reasoning="Mode not specified; defaulted to 'driving' per Rule 3 (optional arg).",
        ))
        try:
            d = route("How long would it take to get from downtown Chicago to O'Hare?")
            self.assertEqual(d.tool_called, "get_travel_time")
            self.assertEqual(d.arguments["mode"], "driving")
            self.assertFalse(d.needs_clarification)
            # Rule 3: optional-arg defaults must NOT appear in assumptions_made
            mode_logged = any("mode" in a.lower() or "driving" in a.lower()
                              for a in d.assumptions_made)
            self.assertFalse(mode_logged,
                "Optional arg default 'driving' should not appear in assumptions_made (Rule 3)")
        finally:
            p.stop()

    # 9 ── multi-tool: travel is primary, weather is secondary ─────────────────

    def test_09_multi_tool_primary_travel(self):
        p = _patch(_mock_decision(
            tool_called="get_travel_time",
            arguments={"origin": "Paris", "destination": "Amsterdam", "mode": "driving"},
            confidence="medium",
            needs_clarification=False,
            clarifying_question=None,
            assumptions_made=["Interpreted 'tomorrow' as the travel date for context."],
            reasoning=(
                "Primary intent is travel duration (Paris → Amsterdam). "
                "Secondary need is get_weather for Amsterdam; deprioritised as the "
                "user's main question is about the drive time."
            ),
        ))
        try:
            d = route(
                "I'm driving from Paris to Amsterdam tomorrow — "
                "how long will it take and what's the weather forecast for Amsterdam?"
            )
            self.assertEqual(d.tool_called, "get_travel_time")
            self.assertEqual(d.confidence, "medium")
            self.assertFalse(d.needs_clarification)
            # Reasoning must acknowledge the secondary tool
            self.assertIn("get_weather", d.reasoning)
        finally:
            p.stop()

    # 10 ── out of scope ────────────────────────────────────────────────────────

    def test_10_out_of_scope(self):
        p = _patch(_mock_decision(
            tool_called=None,
            arguments={},
            confidence="high",
            needs_clarification=False,
            clarifying_question=None,
            assumptions_made=[],
            reasoning=(
                "Booking a hotel is out of scope. "
                "None of the available tools (get_weather, get_travel_time, "
                "convert_currency) support reservations."
            ),
        ))
        try:
            d = route("Can you book me a hotel in Rome for next weekend?")
            self.assertIsNone(d.tool_called)
            self.assertFalse(d.needs_clarification)
            self.assertIn("out of scope", d.reasoning.lower())
        finally:
            p.stop()

    # 11 ── present but invalid arg: bad currency code ─────────────────────────
    # "Mars credits" is present but not a real ISO 4217 code — Rule 1b.

    def test_11_invalid_currency_code(self):
        p = _patch(_mock_decision(
            tool_called=None,
            arguments={},
            confidence="low",
            needs_clarification=True,
            clarifying_question=(
                "'Mars credits' is not a recognised ISO 4217 currency code. "
                "Which currency would you like to convert 100 dollars into?"
            ),
            assumptions_made=[],
            reasoning=(
                "Rule 1b: to_currency is present but invalid ('Mars credits'). "
                "Treating as missing — asking for a valid currency code."
            ),
        ))
        try:
            d = route("Convert 100 dollars to Mars credits.")
            self.assertTrue(d.needs_clarification)
            self.assertIsNotNone(d.clarifying_question)
            self.assertIsNone(d.tool_called)
            self.assertEqual(d.arguments, {})
        finally:
            p.stop()

    # 12 ── ambiguous entity: multiple valid Springfields ──────────────────────
    # Soft: model may ask OR proceed with a logged assumption.

    def test_12_ambiguous_springfield(self):
        # Mocking the Rule-2 path (proceed with assumption) as the ideal outcome.
        p = _patch(_mock_decision(
            tool_called="get_weather",
            arguments={"location": "Springfield, IL", "date": "tomorrow"},
            confidence="medium",
            needs_clarification=False,
            clarifying_question=None,
            assumptions_made=["Interpreted 'Springfield' as Springfield, IL (most populous)."],
            reasoning=(
                "Rule 2: 'Springfield' is vague but resolvable. "
                "Defaulting to Springfield, IL and logging the assumption."
            ),
        ))
        try:
            d = route("What's the weather in Springfield tomorrow?")
            # Soft: either clarification OR get_weather with assumption logged is valid.
            if d.needs_clarification:
                self.assertIsNotNone(d.clarifying_question,
                    "If needs_clarification, clarifying_question must be set")
            else:
                self.assertEqual(d.tool_called, "get_weather")
                self.assertTrue(
                    any("springfield" in a.lower() for a in d.assumptions_made),
                    "Ambiguous location must be logged in assumptions_made"
                )
        finally:
            p.stop()

    # 13 ── ambiguous routing: weather vs general knowledge ─────────────────────
    # Soft: get_weather OR null (general climate knowledge) are both valid.

    def test_13_ambiguous_weather_or_knowledge(self):
        p = _patch(_mock_decision(
            tool_called="get_weather",
            arguments={"location": "Reykjavik", "date": "2025-08-23"},
            confidence="medium",
            needs_clarification=False,
            clarifying_question=None,
            assumptions_made=["Resolved 'this time of year' to the current date 2025-08-23."],
            reasoning=(
                "Rule 2: 'this time of year' is vague but resolvable to today's date. "
                "Routing to get_weather for a concrete forecast."
            ),
        ))
        try:
            d = route("What's Reykjavik like this time of year?")
            # Soft: get_weather or null both acceptable; check internal consistency.
            if d.tool_called == "get_weather":
                self.assertIn("location", d.arguments)
                self.assertIn("date", d.arguments)
                self.assertFalse(d.needs_clarification)
            else:
                self.assertIsNone(d.tool_called)
                self.assertFalse(d.needs_clarification)
        finally:
            p.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
