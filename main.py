"""Decision loop: read a request, route it, optionally execute the mock tool."""

import json
import sys

from agent import route
from tools import TOOL_REGISTRY


def run(request: str) -> None:
    print(f"\nRequest: {request}")
    print("-" * 60)

    decision = route(request)
    output = decision.to_dict()

    print(json.dumps(output, indent=2))

    if decision.needs_clarification:
        print(f"\nNeeds clarification: {decision.clarifying_question}")
        return

    if not decision.tool_called:
        print("\nNo tool matched.")
        return

    tool_fn = TOOL_REGISTRY.get(decision.tool_called)
    if tool_fn is None:
        print(f"\nUnknown tool: {decision.tool_called}")
        return

    try:
        result = tool_fn(**decision.arguments)
        print(f"\nTool result ({decision.tool_called}):")
        print(json.dumps(result, indent=2))
    except TypeError as exc:
        print(f"\nTool call failed — bad arguments: {exc}")


def repl() -> None:
    print("Trip-planning agent. Type a request (or 'quit' to exit).\n")
    while True:
        try:
            request = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not request:
            continue
        if request.lower() in {"quit", "exit", "q"}:
            break
        run(request)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Single-shot: python main.py "what's the weather in Paris tomorrow?"
        run(" ".join(sys.argv[1:]))
    else:
        repl()
