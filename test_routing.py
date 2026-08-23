"""
Eval harness for routing-agent behaviour — requires a live Anthropic API key.

Usage
-----
    export ANTHROPIC_API_KEY=sk-ant-...
    python -m unittest test_routing -v

These tests call the real Claude API and assert that the model's routing
decisions match the ambiguity policy defined in agent.py.  They are
intentionally NOT mocked: the point is to catch regressions in prompt
behaviour, not in Python parsing logic.

response field contract
-----------------------
• needs_clarification=true  → response == clarifying_question (verbatim copy per prompt)
• tool_called=<tool>        → response is non-empty natural-language answer generated
                              from the mock tool result (second Claude call in agent.py)
• tool_called=null          → response is a direct answer (1-2 sentences)

To convert a test into a mocked unit test for offline development, wrap
the route() call in:
    with patch("agent.anthropic.Anthropic") as m:
        m.return_value.messages.create.return_value = <fake_response>
        ...
and remove the @skipUnless guard.
"""

import os
import unittest

from agent import route


@unittest.skipUnless(os.getenv("ANTHROPIC_API_KEY"), "set ANTHROPIC_API_KEY to run evals")
class TestRouting(unittest.TestCase):

    # 1 ── clear single tool: get_weather ─────────────────────────────────────

    def test_01_clear_weather(self):
        d = route("What's the weather in London on 2025-09-01?")
        self.assertEqual(d.tool_called, "get_weather")
        self.assertEqual(d.arguments.get("location"), "London")
        self.assertEqual(d.arguments.get("date"), "2025-09-01")
        self.assertEqual(d.confidence, "high")
        self.assertFalse(d.needs_clarification)
        self.assertIsNone(d.clarifying_question)
        self.assertEqual(d.assumptions_made, [])
        # response: natural-language summary of weather result
        self.assertIsInstance(d.response, str)
        self.assertGreater(len(d.response), 0)

    # 2 ── clear single tool: get_travel_time ─────────────────────────────────

    def test_02_clear_travel_time(self):
        d = route("How long does it take to drive from Berlin to Munich?")
        self.assertEqual(d.tool_called, "get_travel_time")
        self.assertEqual(d.arguments.get("origin"), "Berlin")
        self.assertEqual(d.arguments.get("destination"), "Munich")
        self.assertEqual(d.arguments.get("mode"), "driving")
        self.assertEqual(d.confidence, "high")
        self.assertFalse(d.needs_clarification)
        # response: natural-language travel-time summary
        self.assertIsInstance(d.response, str)
        self.assertGreater(len(d.response), 0)

    # 3 ── clear single tool: convert_currency ────────────────────────────────

    def test_03_clear_currency(self):
        d = route("Convert 250 USD to JPY.")
        self.assertEqual(d.tool_called, "convert_currency")
        self.assertEqual(d.arguments.get("amount"), 250.0)
        self.assertEqual(d.arguments.get("from_currency"), "USD")
        self.assertEqual(d.arguments.get("to_currency"), "JPY")
        self.assertEqual(d.confidence, "high")
        self.assertFalse(d.needs_clarification)
        self.assertEqual(d.assumptions_made, [])
        # response: natural-language conversion result
        self.assertIsInstance(d.response, str)
        self.assertGreater(len(d.response), 0)

    # 4 ── no tool needed: in-scope general knowledge ─────────────────────────

    def test_04_no_tool_general_knowledge(self):
        d = route("What currency does Japan use?")
        self.assertIsNone(d.tool_called)
        self.assertEqual(d.arguments, {})
        self.assertFalse(d.needs_clarification)
        self.assertIsNone(d.clarifying_question)
        # response: direct answer from Claude
        self.assertIsInstance(d.response, str)
        self.assertGreater(len(d.response), 0)

    # 5 ── missing required arg: no location for weather ──────────────────────

    def test_05_missing_location(self):
        d = route("What's the weather going to be like tomorrow?")
        self.assertTrue(d.needs_clarification)
        self.assertIsNotNone(d.clarifying_question)
        self.assertIsNone(d.tool_called)
        self.assertEqual(d.arguments, {})
        # response must be the clarifying question verbatim
        self.assertEqual(d.response, d.clarifying_question)

    # 6 ── missing required arg: no target currency ───────────────────────────

    def test_06_missing_target_currency(self):
        d = route("How much is 80 euros worth?")
        self.assertTrue(d.needs_clarification)
        self.assertIsNotNone(d.clarifying_question)
        self.assertIsNone(d.tool_called)
        # response must be the clarifying question verbatim
        self.assertEqual(d.response, d.clarifying_question)

    # 7 ── "the city" has no referent — Rule 1, not Rule 2 ────────────────────

    def test_07_irresolvable_location(self):
        d = route("Will it rain in the city next Tuesday?")
        self.assertTrue(d.needs_clarification)
        self.assertIsNotNone(d.clarifying_question)
        self.assertIsNone(d.tool_called)
        # response must be the clarifying question verbatim
        self.assertEqual(d.response, d.clarifying_question)

    # 8 ── optional mode omitted → silent default, NOT logged ─────────────────

    def test_08_optional_mode_defaulted(self):
        d = route("How long would it take to get from downtown Chicago to O'Hare?")
        self.assertEqual(d.tool_called, "get_travel_time")
        self.assertEqual(d.arguments.get("mode"), "driving")
        self.assertFalse(d.needs_clarification)
        # Rule 3: optional-arg defaults must NOT appear in assumptions_made
        mode_logged = any(
            "mode" in a.lower() or "driving" in a.lower()
            for a in d.assumptions_made
        )
        self.assertFalse(
            mode_logged,
            "Optional arg default 'driving' should not appear in assumptions_made (Rule 3)",
        )
        # response: natural-language travel-time summary
        self.assertIsInstance(d.response, str)
        self.assertGreater(len(d.response), 0)

    # 9 ── multi-tool: travel primary, weather secondary ──────────────────────

    def test_09_multi_tool_primary_travel(self):
        d = route(
            "I'm driving from Paris to Amsterdam tomorrow — "
            "how long will it take and what's the weather forecast for Amsterdam?"
        )
        self.assertEqual(d.tool_called, "get_travel_time")
        self.assertEqual(d.confidence, "medium")
        self.assertFalse(d.needs_clarification)
        # Prompt requires secondary tool to be named in reasoning
        self.assertIn("get_weather", d.reasoning)
        # response: natural-language travel-time summary
        self.assertIsInstance(d.response, str)
        self.assertGreater(len(d.response), 0)

    # 10 ── out of scope ───────────────────────────────────────────────────────

    def test_10_out_of_scope(self):
        d = route("Can you book me a hotel in Rome for next weekend?")
        self.assertIsNone(d.tool_called)
        self.assertFalse(d.needs_clarification)
        # response: direct explanation from Claude
        self.assertIsInstance(d.response, str)
        self.assertGreater(len(d.response), 0)

    # 11 ── present but invalid arg: unrecognised currency code ───────────────

    def test_11_invalid_currency_code(self):
        d = route("Convert 100 dollars to Mars credits.")
        self.assertTrue(d.needs_clarification)
        self.assertIsNotNone(d.clarifying_question)
        self.assertIsNone(d.tool_called)
        self.assertEqual(d.arguments, {})
        # response must be the clarifying question verbatim
        self.assertEqual(d.response, d.clarifying_question)

    # 12 ── ambiguous entity: multiple Springfields (soft) ────────────────────
    # Acceptable: clarification OR get_weather with assumption logged.

    def test_12_ambiguous_springfield(self):
        d = route("What's the weather in Springfield tomorrow?")
        self.assertIsInstance(d.response, str)
        self.assertGreater(len(d.response), 0, "response must be non-empty")
        if d.needs_clarification:
            self.assertIsNotNone(d.clarifying_question)
            self.assertEqual(d.response, d.clarifying_question)
        else:
            self.assertEqual(d.tool_called, "get_weather")
            self.assertTrue(
                any("springfield" in a.lower() for a in d.assumptions_made),
                "Ambiguous location choice must be logged in assumptions_made",
            )

    # 13 ── ambiguous routing: weather vs general knowledge (soft) ────────────
    # Acceptable: get_weather with resolved date, OR tool_called=null.

    def test_13_ambiguous_weather_or_knowledge(self):
        d = route("What's Reykjavik like this time of year?")
        self.assertFalse(d.needs_clarification)
        self.assertIsInstance(d.response, str)
        self.assertGreater(len(d.response), 0, "response must be non-empty")
        if d.tool_called == "get_weather":
            self.assertIn("location", d.arguments)
            self.assertIn("date", d.arguments)
        else:
            self.assertIsNone(d.tool_called)


if __name__ == "__main__":
    unittest.main(verbosity=2)
