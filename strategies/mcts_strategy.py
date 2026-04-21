"""
MCTS-based trading strategy.
Uses the Rust MCTS engine via JSON bridge (or PyO3 when compiled).
Connects to real market data for position evaluation.
"""
import json
import os
import subprocess
import random
from typing import Optional, List, Dict
from pathlib import Path

from src.events import EventEmitter, EventKind


class MCTSStrategy:
    """
    Baduk-style MCTS trading strategy.
    - Fetches real market state
    - Converts to GameState for MCTS engine
    - Runs search for best action
    - Executes via connector
    """

    def __init__(self, emitter: EventEmitter, connector=None, bankroll: float = 8000.0):
        self.emitter = emitter
        self.connector = connector
        self.bankroll = bankroll
        self.position = 0.0
        self.entry_price = 0.0
        self.mcts_path = Path.home() / "mcts-trading-engine" / "target" / "release" / "mcts-trader-cli"
        self.use_rust = self.mcts_path.exists()

    def _build_game_state(self, market_data: dict) -> dict:
        """Convert market data to MCTS GameState."""
        price = market_data.get("price", 100.0)
        features = market_data.get("features", [0.0, 0.0, 0.0])
        return {
            "price": price,
            "position": self.position,
            "balance": self.bankroll,
            "timestamp": market_data.get("timestamp", 0),
            "features": features,
        }

    def _run_mcts(self, state: dict, sims: int = 10000) -> dict:
        """Run MCTS search. Falls back to Python heuristic if Rust not available."""
        if self.use_rust:
            try:
                config = {
                    "num_simulations": sims,
                    "exploration_constant": 1.414,
                    "max_depth": 150,
                    "seed": random.randint(0, 2**32),
                }
                result = subprocess.run(
                    [str(self.mcts_path), json.dumps(state), json.dumps(config)],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode == 0:
                    return json.loads(result.stdout)
            except Exception as e:
                self.emitter.emit(EventKind.API_ERROR, provider="mcts_rust", error=str(e))

        # Python fallback: simple edge heuristic
        price = state["price"]
        features = state["features"]
        momentum = features[0] if len(features) > 0 else 0.0

        if momentum > 0.1 and self.position <= 0:
            return {"best_action": "Buy", "estimated_value": momentum}
        elif momentum < -0.1 and self.position >= 0:
            return {"best_action": "Sell", "estimated_value": -momentum}
        return {"best_action": "Hold", "estimated_value": 0.0}

    def evaluate_markets(self, markets: List[dict]) -> Optional[dict]:
        """Run MCTS on each market, return best opportunity."""
        best = None
        best_value = float("-inf")

        for market in markets:
            state = self._build_game_state(market)
            result = self._run_mcts(state)
            value = result.get("estimated_value", 0.0)
            action = result.get("best_action", "Hold")

            if action != "Hold" and value > best_value:
                best_value = value
                best = {
                    "market": market.get("symbol", market.get("slug", "unknown")),
                    "action": action,
                    "price": state["price"],
                    "edge": value,
                    "confidence": min(0.99, value * 2),
                }

        return best

    def size_position(self, edge: dict) -> float:
        """Kelly-based position sizing with 20% max drawdown guard."""
        confidence = edge.get("confidence", 0.5)
        edge_size = abs(edge.get("edge", 0.0))
        # Half-Kelly: f = (p*b - q) / b * 0.5
        # Simplified: use confidence as win prob, edge as odds proxy
        kelly = (confidence * edge_size - (1 - confidence)) / max(edge_size, 0.01)
        kelly = max(0, kelly) * 0.5
        # Cap at 20% of bankroll
        max_risk = self.bankroll * 0.20
        position_value = min(self.bankroll * kelly, max_risk)
        return position_value / edge["price"]
