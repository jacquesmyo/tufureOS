"""
Backtest engine for strategy validation.
Uses real historical data (from Binance klines or CSV).
Tracks PnL, Sharpe, max drawdown, win rate.
"""
import json
from typing import List, Dict, Callable, Optional
from statistics import mean, stdev
from pathlib import Path


class BacktestEngine:
    """
    Event-driven backtest engine.
    - No lookahead bias
    - Realistic fee model
    - Tracks full equity curve
    """

    def __init__(self, initial_bankroll: float = 8000.0, fee_rate: float = 0.001):
        self.initial = initial_bankroll
        self.bankroll = initial_bankroll
        self.fee_rate = fee_rate
        self.position = 0.0
        self.trades = []
        self.equity_curve = []
        self.peak = initial_bankroll
        self.max_dd = 0.0

    def reset(self):
        self.bankroll = self.initial
        self.position = 0.0
        self.trades = []
        self.equity_curve = []
        self.peak = self.initial
        self.max_dd = 0.0

    def _update_equity(self, price: float):
        equity = self.bankroll + self.position * price
        self.equity_curve.append(equity)
        if equity > self.peak:
            self.peak = equity
        dd = (self.peak - equity) / self.peak
        if dd > self.max_dd:
            self.max_dd = dd

    def run(self, prices: List[float], strategy_fn: Callable[[List[float]], Optional[dict]]) -> dict:
        """
        Run backtest over price series.
        strategy_fn(prices_so_far) -> {"signal": "Buy|Sell|Hold", "size": float} or None
        """
        self.reset()
        for i in range(len(prices)):
            price = prices[i]
            self._update_equity(price)

            signal = strategy_fn(prices[:i+1])
            if not signal:
                continue

            action = signal.get("signal", "Hold")
            size = signal.get("size", 0.0)

            if action == "Buy" and self.position <= 0:
                cost = size * price * (1 + self.fee_rate)
                if cost <= self.bankroll:
                    self.position = size
                    self.bankroll -= cost
                    self.trades.append({"type": "buy", "price": price, "size": size, "idx": i})

            elif action == "Sell" and self.position >= 0:
                proceeds = size * price * (1 - self.fee_rate)
                if self.position >= size:
                    self.position -= size
                    self.bankroll += proceeds
                    self.trades.append({"type": "sell", "price": price, "size": size, "idx": i})

        # Final mark-to-market
        final_price = prices[-1] if prices else 0
        final_equity = self.bankroll + self.position * final_price
        self._update_equity(final_price)

        return self._report(final_equity)

    def _report(self, final_equity: float) -> dict:
        total_return = (final_equity - self.initial) / self.initial
        wins = sum(1 for t in self.trades if t["type"] == "sell")
        win_rate = wins / len(self.trades) if self.trades else 0.0

        # Sharpe from equity curve (daily-ish approx)
        if len(self.equity_curve) > 1:
            returns = [(self.equity_curve[i] - self.equity_curve[i-1]) / self.equity_curve[i-1]
                       for i in range(1, len(self.equity_curve))]
            avg_ret = mean(returns) if returns else 0.0
            std_ret = stdev(returns) if len(returns) > 1 else 0.0
            sharpe = (avg_ret * 252) / (std_ret * (252**0.5)) if std_ret > 0 else 0.0
        else:
            sharpe = 0.0

        return {
            "initial_bankroll": self.initial,
            "final_equity": final_equity,
            "total_return": total_return,
            "max_drawdown": self.max_dd,
            "sharpe_ratio": sharpe,
            "trades": len(self.trades),
            "win_rate": win_rate,
            "equity_curve": self.equity_curve,
        }

    def save_report(self, path: str, strategy_name: str = "unknown"):
        report = self._report(self.equity_curve[-1] if self.equity_curve else self.initial)
        report["strategy"] = strategy_name
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(report, f, indent=2)
