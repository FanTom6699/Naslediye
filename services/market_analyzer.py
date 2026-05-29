from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass

import pandas as pd

from config import Settings
from services.indicators import atr, ema, rsi
from services.signal_selector import SignalCandidate


@dataclass(frozen=True)
class Candle:
    symbol: str
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketAnalyzer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.max_candles = max(settings.ema_slow + 20, 260)
        self.candles: dict[str, deque[Candle]] = defaultdict(lambda: deque(maxlen=self.max_candles))
        self.latest_price: dict[str, float] = {}

    def update_candle(self, candle: Candle) -> None:
        self.candles[candle.symbol].append(candle)
        self.latest_price[candle.symbol] = candle.close

    def get_price(self, symbol: str) -> float | None:
        return self.latest_price.get(symbol)

    def get_symbols(self) -> list[str]:
        return sorted(self.candles.keys())

    def analyze_all(self) -> list[SignalCandidate]:
        out: list[SignalCandidate] = []
        for symbol in self.get_symbols():
            candidate = self.analyze_symbol(symbol)
            if candidate is not None:
                out.append(candidate)
        return out

    def analyze_symbol(self, symbol: str) -> SignalCandidate | None:
        buffer = self.candles.get(symbol)
        if not buffer or len(buffer) < self.settings.ema_slow + 5:
            return None

        df = pd.DataFrame(
            {
                "open": [c.open for c in buffer],
                "high": [c.high for c in buffer],
                "low": [c.low for c in buffer],
                "close": [c.close for c in buffer],
                "volume": [c.volume for c in buffer],
            }
        )

        df["ema_fast"] = ema(df["close"], self.settings.ema_fast)
        df["ema_slow"] = ema(df["close"], self.settings.ema_slow)
        df["rsi"] = rsi(df["close"], self.settings.rsi_period)
        df["atr"] = atr(df, self.settings.atr_period)

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        close = float(latest["close"])
        ema_fast_val = float(latest["ema_fast"])
        ema_slow_val = float(latest["ema_slow"])
        atr_val = float(latest["atr"])

        if close <= 0 or atr_val <= 0:
            return None

        trend_strength = abs(ema_fast_val - ema_slow_val) / atr_val
        volatility_ratio = atr_val / close
        is_flat = trend_strength < 0.55
        low_volatility = volatility_ratio < self.settings.min_volatility

        candle_body = abs(float(latest["close"]) - float(latest["open"]))
        noisy_candle = candle_body > atr_val * 2.1

        rsi_prev = float(prev["rsi"])
        rsi_now = float(latest["rsi"])
        rsi_up_reversal = rsi_prev < 48 and rsi_now > rsi_prev and rsi_now < 72
        rsi_down_reversal = rsi_prev > 52 and rsi_now < rsi_prev and rsi_now > 28

        ema_trend_up = ema_fast_val > ema_slow_val
        ema_trend_down = ema_fast_val < ema_slow_val
        price_up = close > ema_slow_val
        price_down = close < ema_slow_val

        direction = "NONE"
        reasons: list[str] = []
        score = 0.0

        if price_up and ema_trend_up and rsi_up_reversal:
            direction = "LONG"
            reasons.extend(
                [
                    "EMA подтверждение",
                    "RSI подтверждение",
                    "тренд",
                    "волатильность",
                    "отсутствие флэта",
                ]
            )
            score += 3.8

        if price_down and ema_trend_down and rsi_down_reversal:
            direction = "SHORT"
            reasons.extend(
                [
                    "EMA подтверждение",
                    "RSI подтверждение",
                    "тренд",
                    "волатильность",
                    "отсутствие флэта",
                ]
            )
            score += 3.8

        if direction == "NONE":
            return None

        if is_flat or low_volatility or noisy_candle:
            return None

        # Exclude contradictory directional patterns.
        if direction == "LONG" and not (price_up and ema_trend_up):
            return None
        if direction == "SHORT" and not (price_down and ema_trend_down):
            return None

        score += min(trend_strength, 3.2)
        score += min(volatility_ratio / max(self.settings.min_volatility, 1e-6), 2.2)

        # Normalize to 1..10
        strength = max(1.0, min(10.0, round(score, 2)))

        return SignalCandidate(
            symbol=symbol,
            direction=direction,
            strength=strength,
            reasons=reasons,
            confidence_flags={
                "trend_strength": trend_strength >= 0.55,
                "not_flat": not is_flat,
                "volatility_ok": not low_volatility,
                "not_noisy": not noisy_candle,
                "time": int(time.time()) > 0,
            },
        )

    def market_state(self, symbol: str, direction: str) -> dict[str, float | bool] | None:
        buffer = self.candles.get(symbol)
        if not buffer or len(buffer) < self.settings.ema_slow + 5:
            return None

        df = pd.DataFrame(
            {
                "open": [c.open for c in buffer],
                "high": [c.high for c in buffer],
                "low": [c.low for c in buffer],
                "close": [c.close for c in buffer],
            }
        )

        df["ema_fast"] = ema(df["close"], self.settings.ema_fast)
        df["ema_slow"] = ema(df["close"], self.settings.ema_slow)
        df["rsi"] = rsi(df["close"], self.settings.rsi_period)
        df["atr"] = atr(df, self.settings.atr_period)
        df["ema50"] = ema(df["close"], 50)
        df["ema200"] = ema(df["close"], 200)

        latest = df.iloc[-1]
        close = float(latest["close"])
        atr_val = float(latest["atr"])
        ema_fast_val = float(latest["ema_fast"])
        ema_slow_val = float(latest["ema_slow"])
        rsi_val = float(latest["rsi"])
        ema50 = float(latest["ema50"])
        ema200 = float(latest["ema200"])

        if close <= 0 or atr_val <= 0:
            return None

        trend_strength = abs(ema_fast_val - ema_slow_val) / atr_val
        ema_distance = abs(ema50 - ema200) / atr_val
        atr_ratio = atr_val / close
        volatility_ratio = atr_val / close
        is_flat = trend_strength < 0.55
        low_volatility = volatility_ratio < self.settings.min_volatility

        trend_up = ema_fast_val > ema_slow_val and close > ema_slow_val
        trend_down = ema_fast_val < ema_slow_val and close < ema_slow_val
        contradiction = (direction == "LONG" and not trend_up) or (direction == "SHORT" and not trend_down)

        if direction == "LONG":
            rsi_direction_score = max(0.0, min(1.0, (rsi_val - 45.0) / 25.0))
        else:
            rsi_direction_score = max(0.0, min(1.0, (55.0 - rsi_val) / 25.0))

        higher_trend_up = ema50 > ema200 and close > ema200
        higher_trend_down = ema50 < ema200 and close < ema200
        higher_trend_ok = (direction == "LONG" and higher_trend_up) or (direction == "SHORT" and higher_trend_down)

        return {
            "trend_strength": trend_strength,
            "ema_distance": ema_distance,
            "rsi": rsi_val,
            "rsi_direction_score": rsi_direction_score,
            "atr": atr_val,
            "atr_ratio": atr_ratio,
            "volatility": volatility_ratio,
            "is_flat": is_flat,
            "low_volatility": low_volatility,
            "contradiction": contradiction,
            "higher_trend_ok": higher_trend_ok,
        }
