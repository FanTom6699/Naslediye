from __future__ import annotations

from dataclasses import dataclass

from config import Settings
from services.ai_filter import AIFilter
from services.market_analyzer import MarketAnalyzer


@dataclass(frozen=True)
class QualityResult:
    accepted: bool
    reason: str
    score: float
    reasons: list[str]
    state: dict[str, float | bool]


class SignalQualityFilter:
    def __init__(self, settings: Settings, analyzer: MarketAnalyzer, ai_filter: AIFilter) -> None:
        self.settings = settings
        self.analyzer = analyzer
        self.ai_filter = ai_filter

    async def evaluate(self, *, pair: str, direction: str, strength: float) -> QualityResult:
        if strength < self.settings.signal_threshold:
            return QualityResult(
                accepted=False,
                reason="Сила сигнала ниже порога",
                score=max(1.0, min(10.0, round(strength, 2))),
                reasons=["Сила сигнала ниже порога"],
                state={},
            )

        state = self.analyzer.market_state(pair, direction)
        if state is None:
            fallback_score = max(1.0, min(10.0, round(strength, 2)))
            if fallback_score < self.settings.signal_threshold:
                return QualityResult(
                    accepted=False,
                    reason="Итоговый рейтинг ниже порога",
                    score=fallback_score,
                    reasons=["Нет market данных и webhook strength ниже порога"],
                    state={},
                )
            return QualityResult(
                accepted=True,
                reason="OK",
                score=fallback_score,
                reasons=["Fallback: нет market данных, использована сила webhook"],
                state={},
            )

        passed: list[str] = []
        failed: list[str] = []

        trend_strength = float(state.get("trend_strength", 0.0))
        ema_distance = float(state.get("ema_distance", 0.0))
        rsi_score = float(state.get("rsi_direction_score", 0.0))
        atr_ratio = float(state.get("atr_ratio", 0.0))
        volatility = float(state.get("volatility", 0.0))
        not_flat = not bool(state.get("is_flat"))
        low_volatility = bool(state.get("low_volatility"))
        contradiction = bool(state.get("contradiction"))
        higher_trend_ok = bool(state.get("higher_trend_ok"))

        if trend_strength >= 0.8:
            passed.append("Сильный тренд")
        else:
            failed.append("Слабый тренд")

        if ema_distance >= 0.5:
            passed.append("EMA50 выше/ниже EMA200 с запасом")
        else:
            failed.append("Малое расстояние между EMA50 и EMA200")

        if rsi_score >= 0.5:
            passed.append("RSI подтверждает направление")
        else:
            failed.append("RSI не подтверждает направление")

        if atr_ratio >= max(self.settings.min_volatility * 1.1, 1e-6):
            passed.append("ATR поддерживает движение")
        else:
            failed.append("ATR слишком низкий")

        if volatility >= self.settings.min_volatility:
            passed.append("Высокая волатильность")
        else:
            failed.append("Низкая волатильность")

        if not_flat:
            passed.append("Нет флэта")
        else:
            failed.append("Флэт")

        if higher_trend_ok:
            passed.append("Старший тренд совпадает")
        else:
            failed.append("Старший тренд конфликтует")

        if contradiction:
            failed.append("Конфликт индикаторов")

        score = 0.0
        score += min(2.0, trend_strength * 1.25)
        score += min(1.6, ema_distance * 1.2)
        score += min(1.2, rsi_score * 1.2)
        score += min(1.3, atr_ratio / max(self.settings.min_volatility, 1e-6) * 0.55)
        score += min(1.5, volatility / max(self.settings.min_volatility, 1e-6) * 0.65)
        score += 1.2 if not_flat else 0.0
        score += 1.2 if higher_trend_ok else 0.0

        normalized_score = max(1.0, min(10.0, round(score, 2)))

        if low_volatility:
            return QualityResult(False, "Низкая волатильность", normalized_score, failed, state)
        if not not_flat:
            return QualityResult(False, "Флэт", normalized_score, failed, state)
        if contradiction:
            return QualityResult(False, "Конфликт индикаторов", normalized_score, failed, state)
        if not higher_trend_ok:
            return QualityResult(False, "Старший тренд против сигнала", normalized_score, failed, state)

        ai = await self.ai_filter.evaluate(
            pair=pair,
            direction=direction,
            strength=strength,
            context=state,
        )
        if not ai.accepted:
            return QualityResult(False, f"AI фильтр: {ai.reason}", normalized_score, failed, state)

        if normalized_score < self.settings.signal_threshold:
            return QualityResult(False, "Итоговый рейтинг ниже порога", normalized_score, failed, state)

        return QualityResult(True, "OK", normalized_score, passed, state)
