"""
Example strategy plugin for the trading bot harness.
Users inject their logic via hooks. This is a dummy example.
Replace with your real Polymarket + Groq strategy.
"""

import random
from typing import Optional

from src.bot import TradingBot
from src.events import EventEmitter, EventKind


class DummyStrategy:
    """Minimal example showing hook injection."""

    def __init__(self, bot: TradingBot):
        self.bot = bot
        self.emitter: EventEmitter = bot.emitter

        # Wire hooks into the harness
        bot.preflight_hook = self.preflight
        bot.scan_hook = self.scan
        bot.edge_hook = self.edge
        bot.order_hook = self.order
        bot.settle_hook = self.settle

    def preflight(self) -> bool:
        """Check bankroll, API keys, etc."""
        self.emitter.emit(EventKind.BANKROLL_UPDATE, bankroll=252.0)
        return True

    def scan(self) -> list[dict]:
        """Fetch markets. Replace with real Polymarket CLOB calls."""
        markets = [
            {"id": "weather-nyc-25c", "name": "NYC > 25C", "yes_price": 0.45, "no_price": 0.55},
            {"id": "crypto-btc-100k", "name": "BTC > 100k", "yes_price": 0.62, "no_price": 0.38},
        ]
        self.emitter.emit(EventKind.MARKET_FETCHED, count=len(markets))
        return markets

    def edge(self, markets: list[dict]) -> Optional[dict]:
        """Find an edge. Replace with your Groq-powered analysis."""
        best = None
        best_edge = 0.0
        for m in markets:
            # Dummy edge: price deviation from 0.5
            edge = abs(m["yes_price"] - 0.5)
            if edge > best_edge and edge > 0.05:  # min edge threshold
                best_edge = edge
                best = m

        if best:
            side = "yes" if best["yes_price"] < 0.5 else "no"
            return {
                "market": best["id"],
                "side": side,
                "price": best[f"{side}_price"],
                "edge": round(best_edge, 4),
                "confidence": random.uniform(0.6, 0.9),
            }
        return None

    def order(self, edge: dict) -> dict:
        """Place order. Replace with real Polymarket order execution."""
        order_id = f"ord_{random.randint(1000, 9999)}"
        self.emitter.emit(
            EventKind.ORDER_PLACED,
            market=edge["market"],
            side=edge["side"],
            amount=10,
            order_id=order_id,
        )
        return {
            "order_id": order_id,
            "market": edge["market"],
            "side": edge["side"],
            "amount": 10,
            "status": "pending",
        }

    def settle(self, order: dict) -> bool:
        """Wait for fill / settlement."""
        self.emitter.emit(EventKind.ORDER_FILLED, order_id=order["order_id"])
        return True


def main():
    bot = TradingBot("config.json")
    strategy = DummyStrategy(bot)
    bot.run()


if __name__ == "__main__":
    main()
