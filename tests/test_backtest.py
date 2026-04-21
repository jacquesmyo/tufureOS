"""Unit tests for backtest engine."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest.run_backtest import generate_ou_process, run_hybrid_strategy
from backtest.engine import BacktestEngine


def test_generates_prices():
    prices = generate_ou_process(seed=42, days=10)
    assert len(prices) == 10 * 24
    assert all(p > 0 for p in prices)
    print("PASS: test_generates_prices")


def test_reproducible():
    p1 = generate_ou_process(seed=42, days=10)
    p2 = generate_ou_process(seed=42, days=10)
    assert p1 == p2
    print("PASS: test_reproducible")


def test_backtest_runs():
    prices = generate_ou_process(seed=1, days=30)
    report = run_hybrid_strategy(prices, initial=1000.0)
    assert "total_return" in report
    assert "max_drawdown" in report
    assert "sharpe_ratio" in report
    assert report["trades"] >= 0
    print("PASS: test_backtest_runs")


def test_engine_flat():
    engine = BacktestEngine(initial_bankroll=1000.0)
    prices = [100.0] * 100

    def noop(prices):
        return None

    report = engine.run(prices, noop)
    assert report["trades"] == 0
    assert report["final_equity"] == 1000.0
    print("PASS: test_engine_flat")


if __name__ == "__main__":
    test_generates_prices()
    test_reproducible()
    test_backtest_runs()
    test_engine_flat()
    print("\nAll backtest tests passed!")
