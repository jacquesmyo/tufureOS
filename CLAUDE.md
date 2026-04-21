# Trading Bot — Project Constraints

## Intent
Build an autonomous Polymarket trading bot with event-first logging, explicit state machines, and a Rust MCTS engine for 100-150 move ahead strategy planning.

## Build Commands
- Python: `python -m pytest tests/`
- Rust (future): `cargo check && cargo test`

## Test Commands
- `pytest`

## VibeGuard Active
- 2 universal guards + 68 rules (Python profile)

## Trading Bot Specific Rules

### No Silent Failures
- Every API call must emit an event (success or failure)
- No bare `except:` blocks — always log via EventEmitter
- Recovery loops must emit RECOVERY_TRIGGERED before attempting

### State Machine Discipline
- All state transitions go through TradeStateMachine.transition()
- Invalid transitions emit CYCLE_FAILED and return False
- No direct state mutation outside the state machine

### Event-First Logging
- No `print()` — use EventEmitter.emit()
- All events are JSON-serializable and machine-readable
- Log files are `.jsonl` for downstream processing

### API Key Hygiene
- No hardcoded secrets — env vars only
- Check `GROQ_API_KEY`, `POLYMARKET_API_KEY` in doctor preflight
- Never log API keys in events

### Rust Safety (when MCTS engine is integrated)
- No `unwrap()` in production paths — use `?` or emit recovery event
- No `panic!` — propagate errors to Python orchestrator via PyO3
- Lock ordering: state before market data before bankroll

### Cron & Deployment
- Cron runs every 30 minutes
- Doctor runs before every trading session
- Recovery max 3 attempts before escalation

## Forbidden
- Do not create duplicate strategy modules
- Do not invent Polymarket API endpoints
- Do not hardcode bankroll values
- Do not skip doctor checks in production

## Completion Criteria (BDD Scenarios)
Scenario: Bot starts cleanly
  Given doctor reports "ok"
  When bot starts a trading cycle
  Then state transitions idle -> preflight -> market_scan

Scenario: API failure recovery
  Given API returns 429 rate limit
  When recovery loop triggers
  Then backoff with jitter and retry
  And emit RECOVERY_TRIGGERED event

Scenario: Invalid state transition blocked
  Given state is idle
  When direct transition to order_pending attempted
  Then return False
  And emit CYCLE_FAILED event
