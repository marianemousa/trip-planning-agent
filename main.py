"""Decision loop: read a request, route it, and display the response."""

import json
import sys

from agent import route


def run(request: str) -> None:
    print(f"\nRequest: {request}")
    print("-" * 60)

    decision = route(request)
    print(json.dumps(decision.to_dict(), indent=2))
    print(f"\n→ {decision.response}")


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
