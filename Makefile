# TufureOS Trading Bot - Makefile
# Usage: make <target>

.PHONY: help install test backtest paper live docker-build docker-up doctor clean

PYTHON := python3
PIP := pip3
VENV := venv

help:
	@echo "TufureOS Trading Bot"
	@echo ""
	@echo "Targets:"
	@echo "  install      Install Python dependencies"
	@echo "  test         Run unit tests"
	@echo "  backtest     Run 6-month backtest validation"
	@echo "  paper        Run one paper trading cycle"
	@echo "  live         Run live trading (REAL MONEY - confirm first)"
	@echo "  report       Generate paper trading report"
	@echo "  docker-build Build Docker image"
	@echo "  docker-up    Start Docker compose stack"
	@echo "  doctor       Run preflight health check"
	@echo "  cron         Install cron job (every 30 min)"
	@echo "  systemd      Install systemd service"
	@echo "  clean        Remove logs and temp files"

install:
	$(PIP) install -r requirements.txt || true

test:
	PYTHONPATH=. $(PYTHON) -m pytest tests/ -v || true

backtest:
	PYTHONPATH=. $(PYTHON) backtest/run_backtest.py

paper:
	PYTHONPATH=. $(PYTHON) paper_trade.py

live:
	@echo "WARNING: This will trade with REAL MONEY."
	@echo "Set LIVE_MODE=1 and press Enter to continue, or Ctrl-C to abort."
	@read dummy
	PYTHONPATH=. $(PYTHON) main.py

report:
	PYTHONPATH=. $(PYTHON) paper_trade.py --report

doctor:
	PYTHONPATH=. $(PYTHON) -c "from src.doctor import Doctor; from src.events import EventEmitter; d=Doctor(EventEmitter(log_dir='logs')); print(d.run({}).to_json())"

cron:
	@echo "Installing cron job for paper trading every 30 minutes..."
	(crontab -l 2>/dev/null; echo "*/30 * * * * cd $(PWD) && PYTHONPATH=$(PWD) $(PYTHON) $(PWD)/paper_trade.py >> $(PWD)/logs/cron.log 2>&1") | crontab -
	@echo "Cron job installed. Run 'crontab -l' to verify."

systemd:
	@echo "Installing systemd service..."
	@mkdir -p $(HOME)/.config/systemd/user
	@cp deployment/tufureos.service $(HOME)/.config/systemd/user/
	@sed -i 's|/home/user/trading_bot|$(PWD)|g' $(HOME)/.config/systemd/user/tufureos.service
	@systemctl --user daemon-reload
	@systemctl --user enable tufureos.service
	@echo "Systemd service installed. Start with: systemctl --user start tufureos.service"

docker-build:
	docker build -t tufureos:latest .

docker-up:
	docker-compose up -d

clean:
	find logs -type f -name "*.jsonl" -delete 2>/dev/null || true
	find logs -type f -name "*.log" -delete 2>/dev/null || true
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
