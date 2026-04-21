"""Unit tests for trading strategies."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies.mean_reversion import MeanReversionStrategy
from strategies.mcts_strategy import MCTSStrategy
from src.events import EventEmitter


def test_flat_price_holds():
    s = MeanReversionStrategy(period=5, std_mult=2.0)
    prices = [100.0] * 20
    result = s.analyze(prices)
    assert result is None or result["signal"] == "Hold"
    print("PASS: test_flat_price_holds")


def test_buy_on_dip():
    s = MeanReversionStrategy(period=5, std_mult=1.0)
    prices = [100.0, 100.0, 100.0, 100.0, 80.0]
    result = s.analyze(prices)
    assert result is not None
    assert result["signal"] == "Buy"
    assert result["strength"] > 0
    print("PASS: test_buy_on_dip")


def test_sell_on_spike():
    s = MeanReversionStrategy(period=5, std_mult=1.0)
    prices = [100.0, 100.0, 100.0, 100.0, 120.0]
    result = s.analyze(prices)
    assert result is not None
    assert result["signal"] == "Sell"
    assert result["strength"] > 0
    print("PASS: test_sell_on_spike")


def test_mcts_builds_state():
    emitter = EventEmitter(log_dir="/tmp/test_mcts")
    s = MCTSStrategy(emitter, bankroll=1000.0)
    state = {"price": 50.0, "features": [0.1, -0.05, 0.02]}
    gs = s._build_game_state(state)
    assert gs["price"] == 50.0
    assert gs["features"] == [0.1, -0.05, 0.02]
    assert gs["position"] == 0.0
    print("PASS: test_mcts_builds_state")


def test_mcts_returns_action():
    emitter = EventEmitter(log_dir="/tmp/test_mcts2")
    s = MCTSStrategy(emitter, bankroll=1000.0)
    state = {"price": 50.0, "features": [0.1, -0.05, 0.02]}
    gs = s._build_game_state(state)
    result = s._run_mcts(gs, sims=100)
    assert "best_action" in result
    assert result["best_action"] in ("Buy", "Sell", "Hold")
    assert "estimated_value" in result
    print("PASS: test_mcts_returns_action")


def test_mcts_sizing():
    emitter = EventEmitter(log_dir="/tmp/test_mcts3")
    s = MCTSStrategy(emitter, bankroll=1000.0)
    edge = {"edge": 0.50, "price": 100.0, "confidence": 0.95}
    size = s.size_position(edge)
    assert 0 < size <= 200.0  # max 20% of 1000 = 200
    print("PASS: test_mcts_sizing")


if __name__ == "__main__":
    test_flat_price_holds()
    test_buy_on_dip()
    test_sell_on_spike()
    test_mcts_builds_state()
    test_mcts_returns_action()
    test_mcts_sizing()
    print("\nAll strategy tests passed!")
