#!/usr/bin/env python3
"""
Real-time monitor for TufureOS trading bot.
Parses JSONL event logs and exposes metrics.
Can be extended to push to Prometheus, Grafana, or Telegram.
"""
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone


class LogMonitor:
    """Monitors trading bot event logs and generates status reports."""

    def __init__(self, log_dir: str = "logs/paper"):
        self.log_dir = Path(log_dir)
        self.metrics = {
            "total_events": 0,
            "trades": 0,
            "errors": 0,
            "last_trade_time": None,
            "last_error": None,
            "edge_detected_count": 0,
            "edge_rejected_count": 0,
            "cycles_completed": 0,
            "cycles_failed": 0,
        }

    def tail_events(self, follow: bool = False):
        """Yield events from the latest log file."""
        log_files = sorted(self.log_dir.glob("events_*.jsonl"))
        if not log_files:
            print("No log files found.")
            return

        latest = log_files[-1]
        with open(latest) as f:
            if follow:
                f.seek(0, 2)  # Seek to end
                while True:
                    line = f.readline()
                    if not line:
                        time.sleep(1)
                        continue
                    line = line.strip()
                    if line:
                        yield json.loads(line)
            else:
                for line in f:
                    line = line.strip()
                    if line:
                        yield json.loads(line)

    def update_metrics(self, event: dict):
        """Update internal metrics from an event."""
        self.metrics["total_events"] += 1
        event_type = event.get("event", "")

        if event_type == "bot.order.placed":
            self.metrics["trades"] += 1
            self.metrics["last_trade_time"] = event.get("ts")
        elif event_type == "bot.api.error" or event_type == "bot.order.failed":
            self.metrics["errors"] += 1
            self.metrics["last_error"] = event.get("payload", {}).get("error", "unknown")
        elif event_type == "bot.edge.detected":
            self.metrics["edge_detected_count"] += 1
        elif event_type == "bot.edge.rejected":
            self.metrics["edge_rejected_count"] += 1
        elif event_type == "bot.cycle.finished":
            self.metrics["cycles_completed"] += 1
        elif event_type == "bot.cycle.failed":
            self.metrics["cycles_failed"] += 1

    def display(self):
        """Print current metrics."""
        print(f"\n{'='*50}")
        print(f"TufureOS Monitor - {datetime.now(timezone.utc).isoformat()}")
        print(f"{'='*50}")
        for k, v in self.metrics.items():
            print(f"  {k}: {v}")
        print(f"{'='*50}\n")

    def run(self, follow: bool = False):
        """Run the monitor."""
        print(f"Monitoring {self.log_dir}...")
        for event in self.tail_events(follow=follow):
            self.update_metrics(event)
            if not follow:
                continue
            # In follow mode, print key events immediately
            event_type = event.get("event", "")
            if event_type in ("bot.order.placed", "bot.api.error", "bot.cycle.failed"):
                ts = event.get("ts", "?")
                payload = event.get("payload", {})
                if event_type == "bot.order.placed":
                    print(f"[{ts}] TRADE {payload.get('action')} {payload.get('market')} @ {payload.get('price')}")
                elif event_type == "bot.api.error":
                    print(f"[{ts}] ERROR {payload.get('provider')}: {payload.get('error')}")
                elif event_type == "bot.cycle.failed":
                    print(f"[{ts}] CYCLE FAILED: {payload.get('reason')}")

    def generate_status_page(self, output: str = "logs/status.html"):
        """Generate a simple HTML status page."""
        # Process all historical events first
        for event in self.tail_events(follow=False):
            self.update_metrics(event)

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>TufureOS Status</title>
    <meta http-equiv="refresh" content="30">
    <style>
        body {{ font-family: monospace; background: #0d1117; color: #c9d1d9; padding: 20px; }}
        h1 {{ color: #58a6ff; }}
        .metric {{ background: #161b22; padding: 10px; margin: 5px 0; border-radius: 6px; }}
        .ok {{ color: #3fb950; }}
        .warn {{ color: #d29922; }}
        .err {{ color: #f85149; }}
    </style>
</head>
<body>
    <h1>TufureOS Trading Bot</h1>
    <p>Last updated: {datetime.now(timezone.utc).isoformat()}</p>
    <div class="metric">Total Events: {self.metrics['total_events']}</div>
    <div class="metric ok">Trades: {self.metrics['trades']}</div>
    <div class="metric err">Errors: {self.metrics['errors']}</div>
    <div class="metric">Edges Detected: {self.metrics['edge_detected_count']}</div>
    <div class="metric">Edges Rejected: {self.metrics['edge_rejected_count']}</div>
    <div class="metric">Cycles Completed: {self.metrics['cycles_completed']}</div>
    <div class="metric">Cycles Failed: {self.metrics['cycles_failed']}</div>
    <div class="metric">Last Trade: {self.metrics['last_trade_time'] or 'N/A'}</div>
    <div class="metric">Last Error: {self.metrics['last_error'] or 'N/A'}</div>
</body>
</html>"""
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html)
        print(f"Status page written to {output}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="TufureOS Monitor")
    parser.add_argument("--follow", "-f", action="store_true", help="Follow log in real-time")
    parser.add_argument("--status", "-s", action="store_true", help="Generate HTML status page")
    parser.add_argument("--log-dir", default="logs/paper")
    args = parser.parse_args()

    monitor = LogMonitor(log_dir=args.log_dir)

    if args.status:
        monitor.generate_status_page()
        return

    monitor.run(follow=args.follow)
    monitor.display()


if __name__ == "__main__":
    main()
