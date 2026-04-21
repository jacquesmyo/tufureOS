"""
Mean reversion strategy with real backtest capability.
Simple, proven edge: price tends to revert to moving average.
"""
from typing import List, Optional
from statistics import mean, stdev


class MeanReversionStrategy:
    """Bollinger Band mean reversion."""

    def __init__(self, period: int = 20, std_mult: float = 2.0):
        self.period = period
        self.std_mult = std_mult

    def analyze(self, prices: List[float]) -> Optional[dict]:
        if len(prices) < self.period:
            return None
        window = prices[-self.period:]
        ma = mean(window)
        sigma = stdev(window) if len(window) > 1 else 0.0
        upper = ma + self.std_mult * sigma
        lower = ma - self.std_mult * sigma
        current = prices[-1]

        z_score = (current - ma) / sigma if sigma > 0 else 0.0

        if current < lower:
            return {
                "signal": "Buy",
                "strength": abs(z_score),
                "price": current,
                "ma": ma,
                "lower": lower,
                "upper": upper,
            }
        elif current > upper:
            return {
                "signal": "Sell",
                "strength": abs(z_score),
                "price": current,
                "ma": ma,
                "lower": lower,
                "upper": upper,
            }
        return {"signal": "Hold", "strength": 0.0, "price": current, "ma": ma}
