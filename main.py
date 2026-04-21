"""
TufureOS Trading Bot — Real Market Runner
Uses live data, MCTS strategy, event-first logging.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.bot import TradingBot
from src.events import EventKind
from connectors.polymarket import PolymarketConnector
from connectors.binance import BinanceConnector
from strategies.mcts_strategy import MCTSStrategy
from strategies.mean_reversion import MeanReversionStrategy


class RealTradingRunner:
    """Production runner with real connectors."""

    def __init__(self, bot: TradingBot):
        self.bot = bot
        self.poly = PolymarketConnector()
        self.binance = BinanceConnector()
        self.strategy = MCTSStrategy(bot.emitter, bankroll=8000.0)
        self.mean_rev = MeanReversionStrategy()
        self._setup_hooks()

    def _setup_hooks(self):
        self.bot.preflight_hook = self.preflight
        self.bot.scan_hook = self.scan
        self.bot.edge_hook = self.edge
        self.bot.order_hook = self.order
        self.bot.settle_hook = self.settle

    def preflight(self) -> bool:
        """Check APIs are reachable."""
        try:
            health = self.poly._get("https://clob.polymarket.com/health")
            self.bot.emitter.emit(EventKind.BANKROLL_UPDATE, bankroll=8000.0)
            return True
        except Exception as e:
            self.bot.emitter.emit(EventKind.API_ERROR, provider="polymarket", error=str(e))
            return False

    def scan(self) -> list:
        """Fetch real market data."""
        markets = []
        try:
            # Polymarket trending
            events = self.poly.get_trending(limit=10)
            for evt in events:
                m = self.poly.format_market(evt)
                if m and m.get("active"):
                    markets.append(m)
        except Exception as e:
            self.bot.emitter.emit(EventKind.MARKET_ERROR, error=str(e))

        try:
            # Binance BTC as benchmark
            btc_price = self.binance.get_price("BTCUSDT")
            klines = self.binance.get_klines("BTCUSDT", "1h", limit=50)
            closes = [float(k[4]) for k in klines]
            if len(closes) >= 20:
                mr_signal = self.mean_rev.analyze(closes)
                if mr_signal and mr_signal["signal"] != "Hold":
                    markets.append({
                        "symbol": "BTCUSDT",
                        "price": btc_price,
                        "exchange": "binance",
                        "features": [
                            (closes[-1] - closes[-20]) / closes[-20],  # momentum
                            mr_signal.get("strength", 0.0),
                            (btc_price - mr_signal["ma"]) / mr_signal["ma"] if mr_signal["ma"] else 0.0,
                        ],
                    })
        except Exception as e:
            self.bot.emitter.emit(EventKind.MARKET_ERROR, provider="binance", error=str(e))

        self.bot.emitter.emit(EventKind.MARKET_FETCHED, count=len(markets))
        return markets

    def edge(self, markets: list) -> Optional[dict]:
        return self.strategy.evaluate_markets(markets)

    def order(self, edge: dict) -> dict:
        """Log order intent. Real execution requires signed API calls."""
        order_id = f"ord_{edge['market']}_{int(time.time())}"
        size = self.strategy.size_position(edge)
        self.bot.emitter.emit(
            EventKind.ORDER_PLACED,
            market=edge["market"],
            action=edge["action"],
            price=edge["price"],
            size=round(size, 6),
            order_id=order_id,
        )
        return {
            "order_id": order_id,
            "market": edge["market"],
            "action": edge["action"],
            "price": edge["price"],
            "size": size,
            "status": "simulated",
        }

    def settle(self, order: dict) -> bool:
        self.bot.emitter.emit(EventKind.ORDER_FILLED, order_id=order["order_id"])
        return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="TufureOS Real Trading Bot")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--one-shot", action="store_true")
    parser.add_argument("--paper", action="store_true", help="paper trading mode (no real orders)")
    args = parser.parse_args()

    bot = TradingBot(args.config)
    runner = RealTradingRunner(bot)

    if args.one_shot:
        ok = bot.run_cycle()
        bot.emitter.close()
        sys.exit(0 if ok else 1)

    bot.run()


if __name__ == "__main__":
    import time
    main()
