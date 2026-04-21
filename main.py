#!/usr/bin/env python3
"""
TufureOS Trading Bot -- Real Market Runner
Uses live data, MCTS strategy, event-first logging.
Supports both PAPER and LIVE modes.
"""
import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime

from src.events import EventEmitter, EventKind
from src.config import load_config
from src.doctor import Doctor
from src.alerts import AlertManager

from connectors.polymarket import PolymarketConnector
from connectors.binance import BinanceConnector
from connectors.executor import PolymarketExecutor, ExecutionError

from strategies.mean_reversion import MeanReversionStrategy
from strategies.mcts_strategy import MCTSStrategy


LIVE_MODE = os.getenv("LIVE_MODE", "0") == "1"


class LiveTrader:
    """Live trading harness with safety controls."""

    def __init__(self, bankroll: float = 8000.0):
        self.bankroll = bankroll
        self.log_dir = Path(__file__).parent / "logs" / ("live" if LIVE_MODE else "paper")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.emitter = EventEmitter(log_dir=str(self.log_dir))
        self.alerts = AlertManager()
        self.poly = PolymarketConnector()
        self.binance = BinanceConnector()
        self.mcts = MCTSStrategy(self.emitter, bankroll=bankroll)
        self.mean_rev = MeanReversionStrategy(period=20, std_mult=2.0)
        self.prices = []
        self.consecutive_errors = 0
        self.max_consecutive_errors = 3

        if LIVE_MODE:
            self.executor = PolymarketExecutor(self.emitter)
            self.emitter.emit(EventKind.BOT_STARTED, mode="live", bankroll=bankroll)
            self.alerts.send("LIVE MODE ACTIVATED - Real money at risk", level="critical")
        else:
            self.executor = None
            self.emitter.emit(EventKind.BOT_STARTED, mode="paper", bankroll=bankroll)

    def health_check(self) -> bool:
        doc = Doctor(self.emitter)
        report = doc.run({
            "required_env": ["POLYMARKET_API_KEY"] if LIVE_MODE else [],
            "apis": [],
            "check_branch": False,
            "check_cron": False,
        })
        ok = report.overall != "critical"
        self.emitter.emit(EventKind.DOCTOR_RUN, status="ok" if ok else "fail")
        if not ok and LIVE_MODE:
            self.alerts.error_alert("Health check failed in LIVE mode", context="Pre-trade check")
        return ok

    def fetch_data(self):
        markets = []
        try:
            events = self.poly.get_trending(limit=10)
            for evt in events:
                m = self.poly.format_market(evt)
                if m and m.get("active"):
                    markets.append(m)
            self.emitter.emit(EventKind.MARKET_FETCHED, source="polymarket", count=len(markets))
        except Exception as e:
            self.emitter.emit(EventKind.API_ERROR, provider="polymarket", error=str(e))

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
        best_edge = None
        best_value = float("-inf")

        for market in markets:
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
                    "token_id": market.get("token_id"),
                }

        if len(self.prices) >= 20:
            mr = self.mean_rev.analyze(self.prices)
            if mr and mr["signal"] != "Hold" and mr.get("strength", 1.0) > 1.5:
                edge_val = mr["strength"] * 10.0
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
        if not edge:
            self.emitter.emit(EventKind.EDGE_REJECTED, reason="no_edge")
            return

        size = self.mcts.size_position(edge)

        if LIVE_MODE and edge.get("source") == "mcts" and edge.get("token_id"):
            # Execute real order on Polymarket
            try:
                side = "BUY" if edge["action"] == "Buy" else "SELL"
                resp = self.executor.place_market_order(
                    token_id=edge["token_id"],
                    side=side,
                    size=size,
                )
                self.emitter.emit(EventKind.ORDER_FILLED, order_id=resp.get("orderID"), response=resp)
                self.alerts.trade_alert(
                    action=edge["action"],
                    market=edge["market"],
                    price=edge["price"],
                    size=size,
                )
                self.consecutive_errors = 0
            except ExecutionError as e:
                self.emitter.emit(EventKind.ORDER_FAILED, error=str(e))
                self.consecutive_errors += 1
                self.alerts.error_alert(str(e), context="Live order execution")
        else:
            # Paper trade
            order_id = f"paper_{edge['market']}_{int(time.time())}"
            self.emitter.emit(
                EventKind.ORDER_PLACED,
                market=edge["market"],
                action=edge["action"],
                price=edge["price"],
                size=round(size, 6),
                order_id=order_id,
                paper=True,
            )
            self.emitter.emit(EventKind.ORDER_FILLED, order_id=order_id)
            self.alerts.trade_alert(
                action=edge["action"],
                market=edge["market"],
                price=edge["price"],
                size=size,
            )

    def run_cycle(self) -> bool:
        self.emitter.emit(EventKind.BANKROLL_UPDATE, bankroll=self.bankroll)

        if not self.health_check():
            return False

        if self.consecutive_errors >= self.max_consecutive_errors:
            msg = f"Circuit breaker: {self.consecutive_errors} consecutive errors. Pausing."
            self.emitter.emit(EventKind.CYCLE_FAILED, reason="circuit_breaker")
            self.alerts.send(msg, level="critical")
            return False

        markets = self.fetch_data()
        if not markets:
            self.emitter.emit(EventKind.CYCLE_FAILED, reason="no_markets")
            return False

        edge = self.analyze(markets)
        self.execute(edge)
        self.emitter.emit(EventKind.BANKROLL_UPDATE, bankroll=self.bankroll)
        self.emitter.emit(EventKind.CYCLE_FINISHED)
        return True

    def shutdown(self):
        self.emitter.emit(EventKind.BOT_SHUTDOWN)
        self.emitter.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="TufureOS Live Trader")
    parser.add_argument("--bankroll", type=float, default=8000.0)
    parser.add_argument("--daemon", action="store_true", help="Run continuously with sleep")
    parser.add_argument("--interval", type=int, default=1800, help="Cycle interval in seconds (default 1800 = 30min)")
    args = parser.parse_args()

    trader = LiveTrader(bankroll=args.bankroll)

    try:
        if args.daemon:
            print(f"Daemon mode: running every {args.interval}s")
            while True:
                trader.run_cycle()
                time.sleep(args.interval)
        else:
            ok = trader.run_cycle()
            trader.shutdown()
            sys.exit(0 if ok else 1)
    except KeyboardInterrupt:
        print("Shutdown requested")
        trader.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    main()
