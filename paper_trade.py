#!/usr/bin/env python3
"""
Paper trading runner for TufureOS.
Executes one trading cycle: scan -> analyze -> simulate order -> log.
Run via cron every 30 minutes.
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from connectors.polymarket import PolymarketConnector
from connectors.binance import BinanceConnector
from strategies.mean_reversion import MeanReversionStrategy
from strategies.mcts_strategy import MCTSStrategy
from src.events import EventEmitter, EventKind
from src.doctor import Doctor
from src.alerts import AlertManager


class PaperTrader:
    """Paper trading harness with real data, simulated execution."""

    def __init__(self, bankroll: float = 8000.0):
        self.bankroll = bankroll
        self.log_dir = Path(__file__).parent / "logs" / "paper"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.emitter = EventEmitter(log_dir=str(self.log_dir))
        self.poly = PolymarketConnector()
        self.binance = BinanceConnector()
        self.mcts = MCTSStrategy(self.emitter, bankroll=bankroll)
        self.mean_rev = MeanReversionStrategy(period=20, std_mult=2.0)
        self.prices = []  # Price history for Binance BTC
        self.alerts = AlertManager()

    def health_check(self) -> bool:
        """Run /doctor before trading."""
        doc = Doctor(self.emitter)
        report = doc.run({
            "required_env": [],
            "apis": [],
            "check_branch": False,
            "check_cron": False,
        })
        ok = report.overall != "critical"
        self.emitter.emit(EventKind.DOCTOR_RUN, status="ok" if ok else "fail")
        return ok

    def fetch_data(self):
        """Fetch real market data from all sources."""
        markets = []

        # Polymarket
        try:
            events = self.poly.get_trending(limit=10)
            for evt in events:
                m = self.poly.format_market(evt)
                if m and m.get("active"):
                    markets.append(m)
            self.emitter.emit(EventKind.MARKET_FETCHED, source="polymarket", count=len(markets))
        except Exception as e:
            self.emitter.emit(EventKind.API_ERROR, provider="polymarket", error=str(e))

        # Binance BTC
        try:
            btc_price = self.binance.get_price("BTCUSDT")
            klines = self.binance.get_klines("BTCUSDT", "1h", limit=50)
            self.prices = [float(k[4]) for k in klines]
            markets.append({
                "symbol": "BTCUSDT",
                "price": btc_price,
                "exchange": "binance",
                "features": self._compute_features(self.prices),
            })
            self.emitter.emit(EventKind.MARKET_FETCHED, source="binance", count=1)
        except Exception as e:
            self.emitter.emit(EventKind.API_ERROR, provider="binance", error=str(e))

        return markets

    def _compute_features(self, prices: list) -> list:
        if len(prices) < 20:
            return [0.0, 0.0, 0.0]
        momentum = (prices[-1] - prices[-20]) / prices[-20]
        ma20 = sum(prices[-20:]) / 20
        deviation = (prices[-1] - ma20) / ma20 if ma20 else 0.0
        volatility = 0.0
        if len(prices) >= 20:
            mean_p = sum(prices[-20:]) / 20
            variance = sum((p - mean_p) ** 2 for p in prices[-20:]) / 20
            volatility = (variance ** 0.5) / mean_p if mean_p else 0.0
        return [momentum, deviation, volatility]

    def analyze(self, markets: list) -> dict:
        """Run strategies on fetched markets."""
        best_edge = None
        best_value = float("-inf")

        for market in markets:
            # MCTS evaluation
            state = {
                "price": market.get("price", 100.0),
                "features": market.get("features", [0.0, 0.0, 0.0]),
                "timestamp": int(time.time()),
            }
            result = self.mcts._run_mcts(self.mcts._build_game_state(state), sims=5000)
            value = result.get("estimated_value", 0.0)
            action = result.get("best_action", "Hold")

            if action != "Hold" and value > best_value:
                best_value = value
                best_edge = {
                    "market": market.get("symbol", market.get("slug", "unknown")),
                    "action": action,
                    "price": market["price"],
                    "edge": value,
                    "source": "mcts",
                }

        # Also run mean reversion on BTC if we have prices
        if len(self.prices) >= 20:
            mr = self.mean_rev.analyze(self.prices)
            if mr and mr["signal"] != "Hold":
                strength = mr.get("strength", 1.0)
                # Only take strong mean reversion signals
                if strength > 1.5:
                    edge_val = strength * 10.0
                    if edge_val > best_value:
                        best_value = edge_val
                        best_edge = {
                            "market": "BTCUSDT",
                            "action": mr["signal"],
                            "price": mr["price"],
                            "edge": edge_val,
                            "source": "mean_reversion",
                        }

        return best_edge

    def execute(self, edge: dict):
        """Simulate order execution (paper trade)."""
        if not edge:
            self.emitter.emit(EventKind.EDGE_REJECTED, reason="no_edge", timestamp=int(time.time()))
            return

        size = self.mcts.size_position(edge)
        order_id = f"paper_{edge['market']}_{int(time.time())}"

        self.emitter.emit(
            EventKind.ORDER_PLACED,
            market=edge["market"],
            action=edge["action"],
            price=edge["price"],
            size=round(size, 6),
            order_id=order_id,
            source=edge.get("source", "unknown"),
            paper=True,
        )

        # Simulate fill immediately
        self.emitter.emit(EventKind.ORDER_FILLED, order_id=order_id, price=edge["price"])
        self.alerts.trade_alert(
            action=edge["action"],
            market=edge["market"],
            price=edge["price"],
            size=size,
        )

        # Log to dedicated paper trade file
        trade_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "order_id": order_id,
            "market": edge["market"],
            "action": edge["action"],
            "price": edge["price"],
            "size": size,
            "edge": edge["edge"],
            "source": edge.get("source"),
        }
        with open(self.log_dir / "trades.jsonl", "a") as f:
            f.write(json.dumps(trade_record) + "\n")

    def run_cycle(self) -> bool:
        """Run one full paper trading cycle."""
        self.emitter.emit(EventKind.BANKROLL_UPDATE, bankroll=self.bankroll)

        if not self.health_check():
            print("Health check failed - skipping cycle")
            return False

        markets = self.fetch_data()
        if not markets:
            print("No markets fetched - skipping cycle")
            self.emitter.emit(EventKind.CYCLE_FAILED, reason="no_markets")
            return False

        edge = self.analyze(markets)
        self.execute(edge)

        self.emitter.emit(EventKind.BANKROLL_UPDATE, bankroll=self.bankroll)
        return True

    def generate_report(self) -> dict:
        """Generate daily paper trading report from trade log."""
        trades = []
        log_file = self.log_dir / "trades.jsonl"
        if log_file.exists():
            with open(log_file) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        trades.append(json.loads(line))

        if not trades:
            return {"trades": 0, "pnl": 0.0, "status": "no_trades"}

        # Simple PnL estimation (assumes immediate mark-to-market)
        pnl = 0.0
        position = 0.0
        entry_price = 0.0
        for t in trades:
            if t["action"] == "Buy":
                if position <= 0:
                    position = t["size"]
                    entry_price = t["price"]
                else:
                    # Average up
                    total_cost = position * entry_price + t["size"] * t["price"]
                    position += t["size"]
                    entry_price = total_cost / position
            elif t["action"] == "Sell":
                if position > 0:
                    pnl += (t["price"] - entry_price) * min(position, t["size"])
                    position -= t["size"]

        return {
            "trades": len(trades),
            "estimated_pnl": round(pnl, 2),
            "last_trade": trades[-1]["timestamp"] if trades else None,
            "status": "active",
        }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="TufureOS Paper Trader")
    parser.add_argument("--report", action="store_true", help="Generate daily report")
    parser.add_argument("--bankroll", type=float, default=8000.0)
    args = parser.parse_args()

    trader = PaperTrader(bankroll=args.bankroll)

    if args.report:
        report = trader.generate_report()
        print(json.dumps(report, indent=2))
        return

    ok = trader.run_cycle()
    trader.emitter.close()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
