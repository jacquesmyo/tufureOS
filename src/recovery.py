"""
Auto-recovery loops before escalation.
Classify failure mode -> attempt recovery once -> structured escalation if failed.
"""

import random
import time
from typing import Callable, Optional

from src.events import EventEmitter, EventKind
from src.state_machine import State, TradeStateMachine


class FailureClassifier:
    """Classify API / infra failures into retryable buckets."""

    @staticmethod
    def classify(status: Optional[int], error: str) -> tuple[bool, str, float]:
        """
        Returns: (retryable, action, backoff_seconds)
        """
        # Rate limit
        if status == 429:
            return True, "backoff_rate_limit", 30.0

        # Conflict / session expired
        if status == 409:
            return True, "clear_session_retry", 5.0

        # Auth failure
        if status in (401, 403):
            return False, "auth_failure", 0.0

        # Server errors
        if status and status >= 500:
            return True, "server_error_retry", 10.0

        # Timeout / connection
        if any(k in error.lower() for k in ("timeout", "connection", "reset", "refused", "dns")):
            return True, "network_retry", 5.0

        # Unknown
        return True, "unknown_retry", 5.0


class RecoveryLoop:
    """Attempt recovery once before escalating to human."""

    def __init__(
        self,
        emitter: EventEmitter,
        sm: TradeStateMachine,
        max_attempts: int = 3,
        base_backoff: float = 5.0,
    ):
        self.emitter = emitter
        self.sm = sm
        self.max_attempts = max_attempts
        self.base_backoff = base_backoff
        self.attempt = 0

    def reset(self) -> None:
        self.attempt = 0

    def attempt_recovery(
        self,
        status: Optional[int],
        error: str,
        recover_fn: Callable[[str], bool],
    ) -> bool:
        retryable, action, backoff = FailureClassifier.classify(status, error)

        if not retryable:
            self.emitter.emit(
                EventKind.RECOVERY_FAILED,
                action=action,
                attempt=self.attempt,
                max_attempts=self.max_attempts,
                detail=f"non-retryable: {error}",
            )
            self.sm.transition(State.FAILED, f"non_retryable:{action}")
            return False

        self.attempt += 1
        if self.attempt > self.max_attempts:
            self.emitter.emit(
                EventKind.RECOVERY_FAILED,
                action=action,
                attempt=self.attempt,
                max_attempts=self.max_attempts,
                detail="max attempts exceeded",
            )
            self.sm.transition(State.FAILED, "max_recovery_attempts")
            return False

        # Jittered backoff
        jitter = random.uniform(0.5, 1.5)
        sleep = backoff * jitter * self.attempt
        self.emitter.emit(
            EventKind.RECOVERY_TRIGGERED,
            action=action,
            attempt=self.attempt,
            max_attempts=self.max_attempts,
            backoff_seconds=round(sleep, 2),
            detail=error,
        )
        time.sleep(sleep)

        success = recover_fn(action)

        if success:
            self.emitter.emit(
                EventKind.RECOVERY_SUCCESS,
                action=action,
                attempt=self.attempt,
                detail="recovered",
            )
            self.attempt = 0
            return True
        else:
            self.emitter.emit(
                EventKind.RECOVERY_FAILED,
                action=action,
                attempt=self.attempt,
                max_attempts=self.max_attempts,
                detail="recover_fn returned false",
            )
            return False
