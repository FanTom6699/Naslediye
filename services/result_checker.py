from __future__ import annotations

from services.signal_selector import ActiveSignal


class ResultChecker:
    def evaluate(self, signal: ActiveSignal, close_price: float) -> str:
        if close_price == signal.entry_price:
            return "DRAW"

        if signal.direction == "LONG":
            return "WIN" if close_price > signal.entry_price else "LOSS"

        return "WIN" if close_price < signal.entry_price else "LOSS"
