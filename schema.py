from dataclasses import dataclass, field
from typing import Optional, List, Literal


@dataclass
class RoutingDecision:
    tool_called: Optional[str]
    arguments: dict
    confidence: Literal["high", "medium", "low"]
    needs_clarification: bool
    clarifying_question: Optional[str]
    assumptions_made: List[str]
    reasoning: str
    response: str

    def to_dict(self) -> dict:
        return {
            "tool_called": self.tool_called,
            "arguments": self.arguments,
            "confidence": self.confidence,
            "needs_clarification": self.needs_clarification,
            "clarifying_question": self.clarifying_question,
            "assumptions_made": self.assumptions_made,
            "reasoning": self.reasoning,
            "response": self.response,
        }
