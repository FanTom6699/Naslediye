from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class SignalCandidate:
    symbol: str
    direction: str
    strength: float
    reasons: list[str]
    confidence_flags: dict[str, bool]


@dataclass
class ActiveSignal:
    signal_id: int
    symbol: str
    direction: str
    strength: float
    reasons: list[str]
    entry_price: float
    created_at: int
    expires_at: int


class SignalSelector:
    def __init__(self) -> None:
        self.enabled: bool = False
        self.active_signal: ActiveSignal | None = None

    def start(self) -> None:
        self.enabled = True

    def stop(self) -> None:
        self.enabled = False

    def has_active_signal(self) -> bool:
        return self.active_signal is not None

    def choose_best(self, candidates: list[SignalCandidate], threshold: float) -> SignalCandidate | None:
        if not candidates:
            return None

        candidates = sorted(candidates, key=lambda item: item.strength, reverse=True)
        top = candidates[0]
        if top.strength < threshold:
            return None
        return top

    def activate(
        self,
        signal_id: int,
        candidate: SignalCandidate,
        entry_price: float,
        expiration_seconds: int,
    ) -> ActiveSignal:
        now = int(time.time())
        active = ActiveSignal(
            signal_id=signal_id,
            symbol=candidate.symbol,
            direction=candidate.direction,
            strength=candidate.strength,
            reasons=candidate.reasons,
            entry_price=entry_price,
            created_at=now,
            expires_at=now + expiration_seconds,
        )
        self.active_signal = active
        return active

    def clear_active(self) -> None:
        self.active_signal = None
