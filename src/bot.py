"""
Main trading bot harness.
Event-first, state-machine driven, doctor-preflight, auto-recovery.
Claw-code philosophy: humans set direction; claws perform the labor.
"""

import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

from src.doctor import Doctor
from src.events import EventEmitter, EventKind
from src.recovery import RecoveryLoop
from src.state_machine import State, TradeStateMachine


class TradingBot:
    """
    Autonomous trading harness.
    - Runs /doctor before every cycle
    - State machine guards all transitions
    - Auto-recovery before escalation
    - Event-first logging (machine-readable JSONL)
    """

    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.config: dict = {}
        self._load_config()

        self.log_dir = Path(self.config.get("log_dir", "logs"))
        self.emitter = EventEmitter(self.log_dir, env=self.config.get("env", "production"))
        self.sm = TradeStateMachine(self.emitter, on_transition=self._on_transition)
        self.recovery = RecoveryLoop(self.emitter, self.sm, max_attempts=self.config.get("max_recovery", 3))
        self._running = False

        # Graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        # Hooks: user injects strategy via these callables
        self.preflight_hook: Optional[Callable[[], bool]] = None
        self.scan_hook: Optional[Callable[[], list[dict]]] = None
        self.edge_hook: Optional[Callable[[list[dict]], Optional[dict]]] = None
        self.order_hook: Optional[Callable[[dict], dict]] = None
        self.settle_hook: Optional[Callable[[dict], bool]] = None

    def _load_config(self) -> None:
        defaults = {
            "env": "production",
            "log_dir": "logs",
            "cycle_interval_seconds": 1800,
            "max_recovery": 3,
            "required_env": ["GROQ_API_KEY", "POLYMARKET_API_KEY"],
            "apis": [
                {"name": "groq", "url": "https://api.groq.com/openai/v1/models", "headers": {}},
                {"name": "polymarket", "url": "https://clob.polymarket.com/health", "headers": {}},
            ],
            "min_disk_gb": 0.5,
            "check_branch": False,
            "check_cron": True,
            "base_branch": "main",
        }
        if self.config_path.exists():
            with open(self.config_path) as f:
                self.config = {**defaults, **json.load(f)}
        else:
            self.config = defaults

    def _on_transition(self, old: State, new: State, reason: str) -> None:
        # claw-code: state machine first
        pass

    def _shutdown(self, signum, frame) -> None:
        self.emitter.emit(EventKind.BOT_SHUTDOWN, signal=signum)
        self._running = False

    def doctor(self) -> bool:
        """Run preflight. Block cycle if critical."""
        doc = Doctor(self.emitter)
        report = doc.run(self.config)
        return report.overall != "critical"

    def _preflight(self) -> bool:
        self.sm.transition(State.PREFLIGHT, "cycle_start")
        if self.preflight_hook:
            ok = self.preflight_hook()
            if not ok:
                self.sm.transition(State.BLOCKED, "preflight_hook_failed")
                return False
        return True

    def _scan(self) -> list[dict]:
        self.sm.transition(State.MARKET_SCAN, "scanning")
        markets = []
        if self.scan_hook:
            try:
                markets = self.scan_hook()
                self.emitter.emit(EventKind.MARKET_FETCHED, count=len(markets))
            except Exception as e:
                self.emitter.emit(EventKind.MARKET_ERROR, error=str(e))
                self._handle_error(None, str(e), State.MARKET_SCAN)
                return []
        return markets

    def _validate_edge(self, markets: list[dict]) -> Optional[dict]:
        self.sm.transition(State.EDGE_VALIDATE, "validating")
        if self.edge_hook:
            try:
                edge = self.edge_hook(markets)
                if edge:
                    self.emitter.emit(
                        EventKind.EDGE_DETECTED,
                        market=edge.get("market"),
                        edge=edge.get("edge"),
                        confidence=edge.get("confidence"),
                    )
                    return edge
                else:
                    self.emitter.emit(EventKind.EDGE_REJECTED, reason="no_edge")
                    self.sm.transition(State.IDLE, "no_edge")
                    return None
            except Exception as e:
                self.emitter.emit(EventKind.EDGE_REJECTED, error=str(e))
                self._handle_error(None, str(e), State.EDGE_VALIDATE)
                return None
        return None

    def _place_order(self, edge: dict) -> Optional[dict]:
        self.sm.transition(State.ORDER_PENDING, "placing_order")
        if self.order_hook:
            try:
                result = self.order_hook(edge)
                self.emitter.emit(
                    EventKind.ORDER_PLACED,
                    market=edge.get("market"),
                    side=result.get("side"),
                    amount=result.get("amount"),
                    order_id=result.get("order_id"),
                )
                return result
            except Exception as e:
                self.emitter.emit(EventKind.ORDER_FAILED, error=str(e))
                self._handle_error(None, str(e), State.ORDER_PENDING)
                return None
        return {}

    def _settle(self, order: dict) -> bool:
        self.sm.transition(State.FILLED, "settling")
        if self.settle_hook:
            try:
                ok = self.settle_hook(order)
                if ok:
                    self.emitter.emit(EventKind.ORDER_FILLED, order_id=order.get("order_id"))
                    self.sm.transition(State.SETTLED, "settled")
                    return True
                else:
                    self.sm.transition(State.BLOCKED, "settle_failed")
                    return False
            except Exception as e:
                self._handle_error(None, str(e), State.FILLED)
                return False
        self.sm.transition(State.SETTLED, "no_settle_hook")
        return True

    def _handle_error(self, status: Optional[int], error: str, ctx_state: State) -> None:
        self.sm.transition(State.BLOCKED, f"error_in_{ctx_state.value}")

        def _recover(action: str) -> bool:
            # Default recovery: reset to idle and retry next cycle
            self.sm.transition(State.IDLE, f"recovered:{action}")
            return True

        recovered = self.recovery.attempt_recovery(status, error, _recover)
        if not recovered:
            self.sm.transition(State.FAILED, "recovery_exhausted")

    def run_cycle(self) -> bool:
        """Execute one full trading cycle. Returns True if settled or no-op."""
        if not self.sm.can_trade:
            self.emitter.emit(EventKind.CYCLE_FAILED, error="state_not_idle", state=self.sm.state.value)
            return False

        # 1. Doctor
        if not self.doctor():
            self.emitter.emit(EventKind.CYCLE_FAILED, error="doctor_critical")
            return False

        # 2. Preflight
        if not self._preflight():
            return False

        # 3. Market scan
        markets = self._scan()
        if self.sm.state != State.MARKET_SCAN:
            return False

        # 4. Edge validation
        edge = self._validate_edge(markets)
        if edge is None:
            return self.sm.state == State.IDLE

        # 5. Place order
        order = self._place_order(edge)
        if order is None:
            return False

        # 6. Settle
        return self._settle(order)

    def run(self) -> None:
        """Main loop. Runs cycles with configured interval."""
        self._running = True
        interval = self.config.get("cycle_interval_seconds", 1800)
        self.emitter.emit(EventKind.BOT_STARTED, interval_seconds=interval)

        while self._running:
            self.run_cycle()
            if self.sm.state == State.FAILED:
                # Pause longer after failure
                pause = interval * 2
                self.emitter.emit(EventKind.CYCLE_FAILED, pause_seconds=pause, reason="state_failed")
            else:
                pause = interval

            # Sleep in chunks so SIGINT can land
            for _ in range(int(pause)):
                if not self._running:
                    break
                time.sleep(1)

        self.emitter.close()


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Trading Bot Harness")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--doctor-only", action="store_true", help="run doctor and exit")
    parser.add_argument("--one-shot", action="store_true", help="run one cycle and exit")
    args = parser.parse_args()

    bot = TradingBot(args.config)

    if args.doctor_only:
        ok = bot.doctor()
        sys.exit(0 if ok else 1)

    if args.one_shot:
        ok = bot.run_cycle()
        bot.emitter.close()
        sys.exit(0 if ok else 1)

    bot.run()


if __name__ == "__main__":
    main()
