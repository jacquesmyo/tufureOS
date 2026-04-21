"""
Event-first structured logging for trading bot.
All state transitions emit typed JSON events to stdout + file.
No more print debugging. Events are machine-readable for downstream claws.
"""

import json
import sys
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class EventKind(str, Enum):
    # Lifecycle
    BOT_STARTED = "bot.lifecycle.started"
    BOT_SHUTDOWN = "bot.lifecycle.shutdown"
    DOCTOR_RUN = "bot.doctor.run"
    DOCTOR_OK = "bot.doctor.ok"
    DOCTOR_FAIL = "bot.doctor.fail"

    # State machine
    STATE_TRANSITION = "bot.state.transition"

    # Market cycle
    CYCLE_STARTED = "bot.cycle.started"
    CYCLE_FINISHED = "bot.cycle.finished"
    CYCLE_FAILED = "bot.cycle.failed"

    # Edge detection
    EDGE_SCANNED = "bot.edge.scanned"
    EDGE_DETECTED = "bot.edge.detected"
    EDGE_REJECTED = "bot.edge.rejected"

    # Order lifecycle
    ORDER_PLACED = "bot.order.placed"
    ORDER_FILLED = "bot.order.filled"
    ORDER_FAILED = "bot.order.failed"
    ORDER_CANCELLED = "bot.order.cancelled"

    # API / infra
    API_REQUEST = "bot.api.request"
    API_RESPONSE = "bot.api.response"
    API_ERROR = "bot.api.error"
    API_RETRY = "bot.api.retry"
    API_RECOVERED = "bot.api.recovered"

    # Recovery
    RECOVERY_TRIGGERED = "bot.recovery.triggered"
    RECOVERY_SUCCESS = "bot.recovery.success"
    RECOVERY_FAILED = "bot.recovery.failed"

    # Market data
    MARKET_FETCHED = "bot.market.fetched"
    MARKET_ERROR = "bot.market.error"

    # Position
    POSITION_UPDATE = "bot.position.update"
    BANKROLL_UPDATE = "bot.bankroll.update"


class EventEmitter:
    """Typed event emitter. All events go to stdout and a log file."""

    def __init__(self, log_dir: Path, env: str = "production"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.env = env
        self._file = None
        self._seq = 0
        self._open_log()

    def _open_log(self) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = self.log_dir / f"events_{ts}.jsonl"
        self._file = open(path, "a", buffering=1)
        self._emit(
            EventKind.BOT_STARTED,
            {"log_file": str(path), "env": self.env}
        )

    def _emit(self, kind: EventKind, payload: dict, meta: Optional[dict] = None) -> dict:
        self._seq += 1
        event = {
            "event": kind.value,
            "seq": self._seq,
            "ts": datetime.now(timezone.utc).isoformat(),
            "epoch": time.time(),
            "env": self.env,
            "payload": payload,
        }
        if meta:
            event["meta"] = meta

        line = json.dumps(event, default=str, separators=(",", ":"))
        print(line, file=sys.stdout, flush=True)
        if self._file:
            self._file.write(line + "\n")
            self._file.flush()
        return event

    def emit(self, kind: EventKind, **kwargs) -> dict:
        """Emit a typed event with arbitrary payload fields."""
        return self._emit(kind, kwargs)

    def state_transition(self, old: str, new: str, reason: str = "") -> dict:
        return self._emit(
            EventKind.STATE_TRANSITION,
            {"from": old, "to": new, "reason": reason}
        )

    def api_error(self, provider: str, status: int, error: str, retryable: bool = False) -> dict:
        return self._emit(
            EventKind.API_ERROR,
            {"provider": provider, "status": status, "error": error, "retryable": retryable}
        )

    def recovery(self, action: str, attempt: int, max_attempts: int, success: bool, detail: str = "") -> dict:
        kind = EventKind.RECOVERY_SUCCESS if success else EventKind.RECOVERY_FAILED
        return self._emit(
            kind,
            {"action": action, "attempt": attempt, "max_attempts": max_attempts, "detail": detail}
        )

    def close(self) -> None:
        self._emit(EventKind.BOT_SHUTDOWN, {})
        if self._file:
            self._file.close()
            self._file = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
