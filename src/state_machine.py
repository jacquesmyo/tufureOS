"""
Explicit trade lifecycle state machine.
No ambiguous states. Every transition is logged.
States: idle -> preflight -> scan -> edge_validate -> order_pending -> filled -> settled -> idle
Failure paths: blocked -> recovery -> retry / failed
"""

from enum import Enum, auto
from typing import Callable, Optional
from src.events import EventEmitter, EventKind


class State(Enum):
    IDLE = "idle"
    PREFLIGHT = "preflight"
    MARKET_SCAN = "market_scan"
    EDGE_VALIDATE = "edge_validate"
    ORDER_PENDING = "order_pending"
    FILLED = "filled"
    SETTLED = "settled"
    BLOCKED = "blocked"
    RECOVERY = "recovery"
    FAILED = "failed"


class TradeStateMachine:
    """Deterministic state machine for a single trade cycle."""

    # Valid transitions
    _edges = {
        State.IDLE: {State.PREFLIGHT, State.BLOCKED},
        State.PREFLIGHT: {State.MARKET_SCAN, State.BLOCKED, State.RECOVERY},
        State.MARKET_SCAN: {State.EDGE_VALIDATE, State.BLOCKED, State.RECOVERY},
        State.EDGE_VALIDATE: {State.ORDER_PENDING, State.IDLE, State.BLOCKED, State.RECOVERY},
        State.ORDER_PENDING: {State.FILLED, State.FAILED, State.BLOCKED, State.RECOVERY},
        State.FILLED: {State.SETTLED, State.BLOCKED, State.RECOVERY},
        State.SETTLED: {State.IDLE},
        State.BLOCKED: {State.RECOVERY, State.FAILED, State.IDLE},
        State.RECOVERY: {State.IDLE, State.PREFLIGHT, State.FAILED},
        State.FAILED: {State.IDLE, State.RECOVERY},
    }

    def __init__(self, emitter: EventEmitter, on_transition: Optional[Callable] = None):
        self._state = State.IDLE
        self._emitter = emitter
        self._on_transition = on_transition
        self._history: list[tuple[str, str, str]] = []

    @property
    def state(self) -> State:
        return self._state

    @property
    def is_terminal(self) -> bool:
        return self._state in {State.SETTLED, State.FAILED}

    @property
    def can_trade(self) -> bool:
        return self._state in {State.IDLE, State.SETTLED, State.FAILED}

    def transition(self, to: State, reason: str = "") -> bool:
        if to not in self._edges.get(self._state, set()):
            self._emitter.emit(
                EventKind.CYCLE_FAILED,
                error=f"invalid_transition",
                from_state=self._state.value,
                to_state=to.value,
                reason=reason,
            )
            return False

        old = self._state
        self._state = to
        self._history.append((old.value, to.value, reason))
        self._emitter.state_transition(old.value, to.value, reason)

        if self._on_transition:
            self._on_transition(old, to, reason)
        return True

    def start_cycle(self) -> bool:
        return self.transition(State.PREFLIGHT, "cycle_start")

    def fail(self, reason: str) -> bool:
        return self.transition(State.FAILED, reason)

    def recover(self, action: str) -> bool:
        return self.transition(State.RECOVERY, action)

    def reset(self) -> bool:
        return self.transition(State.IDLE, "reset")

    def history(self) -> list[dict]:
        return [{"from": f, "to": t, "reason": r} for f, t, r in self._history]
