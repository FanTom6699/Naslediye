from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AIFilterResult:
    accepted: bool
    score: float
    reason: str


class AIFilter:
    """
    Placeholder for future GPT/LLM quality validation.
    Current implementation is permissive and deterministic.
    """

    async def evaluate(self, *, pair: str, direction: str, strength: float, context: dict) -> AIFilterResult:
        if strength <= 0:
            return AIFilterResult(False, 0.0, "Invalid signal strength")
        return AIFilterResult(True, min(10.0, max(1.0, strength)), "AI filter bypass")
