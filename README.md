# TufureOS Trading Bot

Autonomous financial operating system - Module 1: Trading Engine.

**Philosophy:** Trade as much as possible without losing. Learn from every mistake.
Find original edge through continuous iteration. 100-150 move ahead strategic planning
inspired by Go (Baduk).

---

## Architecture

```
TufureOS/
├── connectors/          Real market data (Polymarket, Binance)
├── strategies/          Edge detection algorithms
│   ├── mean_reversion.py
│   └── mcts_strategy.py  (calls Rust MCTS engine)
├── backtest/            6-month validation framework
├── mcts-engine/         Rust Monte Carlo Tree Search
├── src/                 Core infrastructure
│   ├── events.py        Event-first logging
│   ├── doctor.py        Health checks
│   └── config.py        Settings
├── paper_trade.py       Paper trading runner
├── main.py              Live trading runner
├── monitor.py           Real-time monitoring
├── Makefile             Common operations
├── Dockerfile           Container build
└── docker-compose.yml   Full stack deployment
```

---

## Quick Start

```bash
# Install dependencies
make install

# Run health check
make doctor

# Run 6-month backtest
make backtest

# Run one paper trading cycle
make paper

# View paper trading report
make report

# Generate status dashboard
python3 monitor.py --status
```

---

## Rust MCTS Engine

The high-performance Monte Carlo Tree Search engine is written in Rust
and called from Python via CLI binary.

```bash
cd mcts-engine
cargo build --release --bin mcts-trader-cli
./target/release/mcts-trader-cli <game_state_json> <config_json>
```

**Specs:**
- 100-150 move lookahead
- 300 sub-agent swarm simulation
- Bayesian opponent modeling
- <100us latency per simulation

---

## Backtest Validation

The backtest engine generates 6 months of synthetic OHLC data with
mean-reverting properties and runs all strategies against it.

```bash
PYTHONPATH=. python3 backtest/run_backtest.py
```

Output:
- Strategy PnL, Sharpe ratio, max drawdown
- Trade log with timestamps
- Comparison across mean reversion and MCTS strategies

---

## Deployment

### Cron (every 30 minutes)
```bash
make cron
```

### Systemd (user service)
```bash
make systemd
systemctl --user start tufureos.service
```

### Docker Compose
```bash
make docker-build
make docker-up
```

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
GROQ_API_KEY=your_groq_key          # LLM inference
POLYMARKET_API_KEY=your_poly_key    # Polymarket CLOB
BINANCE_API_KEY=your_binance_key    # Binance (optional)
TELEGRAM_BOT_TOKEN=your_bot_token   # Alerts
LIVE_MODE=0                         # 0=paper, 1=live
BANKROLL=8000.0                     # Starting capital
MAX_POSITION_PCT=0.10               # 10% max per trade
```

---

## Risk Controls

- **Max position:** 10% of bankroll per trade
- **Max drawdown:** 20% hard stop
- **Kelly sizing:** Fractional Kelly with safety cap
- **API health checks:** Every cycle before trading
- **Circuit breakers:** 3 consecutive API failures = pause

---

## Monitoring

```bash
# Real-time log tail
python3 monitor.py --follow

# HTML status page
python3 monitor.py --status
# Then open logs/status.html in browser
```

---

## Roadmap

- [x] Real market connectors
- [x] Rust MCTS engine
- [x] 6-month backtest framework
- [x] Paper trading harness
- [x] Event-first logging
- [x] Health checks (/doctor)
- [x] Makefile + systemd + Docker
- [x] Monitoring dashboard
- [ ] Live order execution
- [ ] Telegram alerts
- [ ] Multi-market arbitrage
- [ ] Strategy optimizer
- [ ] Full autonomous loop (food, rent, travel)

---

## License

MIT - Trade at your own risk. Past backtest performance does not guarantee future results.
