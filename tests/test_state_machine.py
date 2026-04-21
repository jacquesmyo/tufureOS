import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.events import EventEmitter, EventKind
from src.state_machine import State, TradeStateMachine


def test_basic_cycle():
    emitter = EventEmitter(Path("logs/test"), env="test")
    sm = TradeStateMachine(emitter)

    assert sm.state == State.IDLE
    assert sm.can_trade is True

    sm.start_cycle()
    assert sm.state == State.PREFLIGHT

    sm.transition(State.MARKET_SCAN, "scan")
    assert sm.state == State.MARKET_SCAN

    sm.transition(State.EDGE_VALIDATE, "edge")
    sm.transition(State.ORDER_PENDING, "order")
    sm.transition(State.FILLED, "fill")
    sm.transition(State.SETTLED, "settle")
    assert sm.state == State.SETTLED
    assert sm.is_terminal is True

    sm.reset()
    assert sm.state == State.IDLE
    emitter.close()
    print("test_basic_cycle PASS")


def test_invalid_transition():
    emitter = EventEmitter(Path("logs/test"), env="test")
    sm = TradeStateMachine(emitter)

    ok = sm.transition(State.ORDER_PENDING, "bad")
    assert ok is False
    assert sm.state == State.IDLE
    emitter.close()
    print("test_invalid_transition PASS")


def test_recovery_path():
    emitter = EventEmitter(Path("logs/test"), env="test")
    sm = TradeStateMachine(emitter)

    sm.start_cycle()
    sm.transition(State.BLOCKED, "api_down")
    sm.recover("clear_session")
    sm.transition(State.IDLE, "recovered")
    assert sm.state == State.IDLE
    emitter.close()
    print("test_recovery_path PASS")


if __name__ == "__main__":
    test_basic_cycle()
    test_invalid_transition()
    test_recovery_path()
