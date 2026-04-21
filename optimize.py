#!/usr/bin/env python3
"""
Strategy parameter optimizer for TufureOS.
Grid-searches mean reversion parameters using the backtest engine.
Finds the parameter set with best Sharpe ratio and lowest drawdown.
"""
import json
import itertools
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent))

from backtest.run_backtest import generate_synthetic_data, BacktestRunner
from strategies.mean_reversion import MeanReversionStrategy
from strategies.mcts_strategy import MCTSStrategy
from src.events import EventEmitter


class StrategyOptimizer:
    """Optimizes strategy parameters via grid search."""

    def __init__(self, bankroll: float = 8000.0):
        self.bankroll = bankroll
        self.results: List[Dict] = []

    def optimize_mean_reversion(self, param_grid: Dict = None) -> Dict:
        """Grid search mean reversion parameters."""
        if param_grid is None:
            param_grid = {
                "period": [10, 15, 20, 25, 30],
                "std_mult": [1.5, 2.0, 2.5, 3.0],
            }

        keys = list(param_grid.keys())
        values = list(param_grid.values())
        best = None
        best_score = float("-inf")

        # Fixed seed for reproducibility
        prices = generate_synthetic_data(
            seed=42,
            n_hours=6 * 30 * 24,  # 6 months
            base_price=50000.0,
        )

        total = len(list(itertools.product(*values)))
        print(f"Optimizing mean reversion: {total} parameter combinations")

        for i, combo in enumerate(itertools.product(*values)):
            params = dict(zip(keys, combo))
            print(f"[{i+1}/{total}] Testing {params}")

            emitter = EventEmitter(log_dir=f"/tmp/opt_{i}")
            strategy = MeanReversionStrategy(**params)
            runner = BacktestRunner(strategy, emitter, self.bankroll)
            runner.run(prices)
            metrics = runner.metrics()

            # Composite score: Sharpe * (1 - max_drawdown) * return
            score = (
                metrics["sharpe"] * 10.0
                + metrics["return_pct"] * 1.0
                - metrics["max_drawdown"] * 50.0
            )

            result = {
                "params": params,
                "metrics": metrics,
                "score": score,
            }
            self.results.append(result)

            if score > best_score:
                best_score = score
                best = result

        return best

    def save_results(self, path: str = "logs/optimization_results.json"):
        """Save all optimization results."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(
                {
                    "best": self.results[0] if self.results else None,
                    "all": sorted(self.results, key=lambda x: x["score"], reverse=True),
                },
                f,
                indent=2,
            )
        print(f"Results saved to {path}")


def main():
    opt = StrategyOptimizer()
    best = opt.optimize_mean_reversion()
    print("\n" + "=" * 50)
    print("OPTIMIZATION COMPLETE")
    print("=" * 50)
    print(f"Best params: {best['params']}")
    print(f"Return: {best['metrics']['return_pct']:.2f}%")
    print(f"Sharpe: {best['metrics']['sharpe']:.2f}")
    print(f"Max Drawdown: {best['metrics']['max_drawdown']:.2f}%")
    print(f"Trades: {best['metrics']['num_trades']}")
    print("=" * 50)
    opt.save_results()


if __name__ == "__main__":
    main()
