"""
Integration runner for all 13 routing test cases.

Requires a live Anthropic API key — each case calls the real Claude API via
agent.route() and checks that the routing decision matches the expected
behaviour defined below.

Usage
-----
    export ANTHROPIC_API_KEY=sk-ant-...
    python tests.py

The script prints a per-case PASS/FAIL with the full routing decision and a
summary at the end. Cases 7, 12, and 13 are "soft" — multiple outcomes are
acceptable — and are checked only for internal consistency rather than an
exact expected tool.

For offline (mocked) routing tests, see test_routing.py (requires API key,
uses unittest with @skipUnless guard). For unit tests of the tool functions
themselves with no API key, see test_tools.py.
"""

import json
from dataclasses import dataclass
from typing import Optional
from agent import route

# ── Test case definitions ────────────────────────────────────────────────────

@dataclass
class Case:
    id: int
    covers: str
    input: str
    expect_tool: Optional[str]           # None means "must be null"
    expect_clarification: bool
    expect_tool_is_null: bool = False    # True when null is the *correct* outcome


CASES = [
    Case(
        id=1, covers="clear single tool — get_weather",
        input="What's the weather in London on 2025-09-01?",
        expect_tool="get_weather", expect_clarification=False,
    ),
    Case(
        id=2, covers="clear single tool — get_travel_time",
        input="How long does it take to drive from Berlin to Munich?",
        expect_tool="get_travel_time", expect_clarification=False,
    ),
    Case(
        id=3, covers="clear single tool — convert_currency",
        input="Convert 250 USD to JPY.",
        expect_tool="convert_currency", expect_clarification=False,
    ),
    Case(
        id=4, covers="no tool needed — in-scope general knowledge",
        input="What currency does Japan use?",
        expect_tool=None, expect_clarification=False, expect_tool_is_null=True,
    ),
    Case(
        id=5, covers="missing required arg — no location for weather",
        input="What's the weather going to be like tomorrow?",
        expect_tool=None, expect_clarification=True,
    ),
    Case(
        id=6, covers="missing required arg — no target currency",
        input="How much is 80 euros worth?",
        expect_tool=None, expect_clarification=True,
    ),
    Case(
        id=7, covers="vague but resolvable — relative date + informal location",
        input="Will it rain in the city next Tuesday?",
        # "the city" may be irresolvable → clarification; or model may infer.
        # Acceptance: either clarification OR get_weather with an assumption logged.
        expect_tool="get_weather", expect_clarification=False,  # soft — see check logic
    ),
    Case(
        id=8, covers="vague but resolvable — unspecified travel mode",
        input="How long would it take to get from downtown Chicago to O'Hare?",
        expect_tool="get_travel_time", expect_clarification=False,
    ),
    Case(
        id=9, covers="multi-tool request",
        input=(
            "I'm driving from Paris to Amsterdam tomorrow — "
            "how long will it take and what's the weather forecast for Amsterdam?"
        ),
        expect_tool="get_travel_time", expect_clarification=False,
    ),
    Case(
        id=10, covers="out of scope",
        input="Can you book me a hotel in Rome for next weekend?",
        expect_tool=None, expect_clarification=False, expect_tool_is_null=True,
    ),
    Case(
        id=11, covers="present but invalid arg — bad currency code",
        input="Convert 100 dollars to Mars credits.",
        # Policy gap: arg is present but invalid. No clear rule → watch what model does.
        expect_tool=None, expect_clarification=True,   # ideal: ask about the bad code
    ),
    Case(
        id=12, covers="ambiguous entity — multiple valid locations",
        input="What's the weather in Springfield tomorrow?",
        # Ideal: ask which Springfield. Acceptable: proceed with an assumption logged.
        expect_tool="get_weather", expect_clarification=False,  # soft — see check logic
    ),
    Case(
        id=13, covers="ambiguous routing — could be weather or general knowledge",
        input="What's Reykjavik like this time of year?",
        # Acceptable: get_weather OR null (general knowledge). Both valid.
        expect_tool="get_weather", expect_clarification=False,  # soft — see check logic
    ),
]

# ── Soft-check cases (multiple valid outcomes) ───────────────────────────────

SOFT_CASES = {
    7:  "Acceptable: get_weather with assumption logged, OR needs_clarification=true for 'the city'",
    12: "Acceptable: get_weather with Springfield assumption logged, OR needs_clarification=true",
    13: "Acceptable: get_weather OR tool_called=null (general knowledge about climate)",
}

# ── Runner ───────────────────────────────────────────────────────────────────

def check(case: Case, decision) -> tuple[bool, str]:
    """Return (passed, failure_reason)."""
    d = decision

    if case.id in SOFT_CASES:
        # For soft cases just verify the response is internally consistent.
        if d.needs_clarification and not d.clarifying_question:
            return False, "needs_clarification=true but clarifying_question is null"
        if not d.needs_clarification and d.clarifying_question:
            return False, "needs_clarification=false but clarifying_question is set"
        return True, ""

    # Clarification check
    if d.needs_clarification != case.expect_clarification:
        return False, (
            f"needs_clarification={d.needs_clarification}, "
            f"expected {case.expect_clarification}"
        )

    # If we expected clarification, that's all we need to verify.
    if case.expect_clarification:
        if not d.clarifying_question:
            return False, "needs_clarification=true but clarifying_question is null"
        return True, ""

    # Tool routing check
    if d.tool_called != case.expect_tool:
        return False, f"tool_called={d.tool_called!r}, expected {case.expect_tool!r}"

    # Null-tool consistency checks
    if case.expect_tool_is_null and d.arguments:
        return False, "tool_called=null but arguments is non-empty"

    return True, ""


def run_all() -> None:
    results = []
    for case in CASES:
        print(f"\n{'─'*64}")
        print(f"[{case.id:02d}] {case.covers}")
        print(f"     Input: {case.input!r}")
        if case.id in SOFT_CASES:
            print(f"     Note:  {SOFT_CASES[case.id]}")

        try:
            decision = route(case.input)
        except Exception as exc:
            print(f"     ERROR: {exc}")
            results.append((case.id, False, f"exception: {exc}"))
            continue

        d = decision.to_dict()
        print(f"     tool_called:         {d['tool_called']}")
        print(f"     confidence:          {d['confidence']}")
        print(f"     needs_clarification: {d['needs_clarification']}")
        if d["clarifying_question"]:
            print(f"     clarifying_question: {d['clarifying_question']}")
        if d["assumptions_made"]:
            print(f"     assumptions_made:    {d['assumptions_made']}")
        print(f"     reasoning:           {d['reasoning']}")

        passed, reason = check(case, decision)
        status = "PASS" if passed else "FAIL"
        print(f"     [{status}]" + (f" — {reason}" if reason else ""))
        results.append((case.id, passed, reason))

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'═'*64}")
    print("SUMMARY")
    print(f"{'═'*64}")
    passed_ids = [id_ for id_, ok, _ in results if ok]
    failed = [(id_, r) for id_, ok, r in results if not ok]
    print(f"Passed: {len(passed_ids)}/{ len(results)} — {passed_ids}")
    if failed:
        print("Failed:")
        for id_, reason in failed:
            case = next(c for c in CASES if c.id == id_)
            print(f"  [{id_:02d}] {case.covers}")
            print(f"       {reason}")


if __name__ == "__main__":
    run_all()
