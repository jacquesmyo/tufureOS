"""
Alert system for TufureOS.
Sends notifications via Telegram when important events occur.
"""
import os
import json
import urllib.request
from datetime import datetime
from typing import Optional


class AlertManager:
    """Sends alerts to configured channels."""

    def __init__(self, telegram_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.telegram_token = telegram_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = bool(self.telegram_token and self.chat_id)

    def send(self, message: str, level: str = "info"):
        """Send an alert. Level: info, warn, error, critical"""
        if not self.enabled:
            print(f"[ALERT {level.upper()}] {message}")
            return

        emoji = {"info": "ℹ️", "warn": "⚠️", "error": "❌", "critical": "🚨"}.get(level, "ℹ️")
        full_msg = f"{emoji} <b>TufureOS {level.upper()}</b>\n{message}\n<code>{datetime.utcnow().isoformat()}</code>"

        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            data = json.dumps({
                "chat_id": self.chat_id,
                "text": full_msg,
                "parse_mode": "HTML",
            }).encode()
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
        except Exception as e:
            print(f"[ALERT FAILED] {message} | Error: {e}")

    def trade_alert(self, action: str, market: str, price: float, size: float, pnl: Optional[float] = None):
        """Alert for trade execution."""
        msg = f"Trade Executed\nAction: {action}\nMarket: {market}\nPrice: {price}\nSize: {size}"
        if pnl is not None:
            msg += f"\nPnL: {pnl:+.2f}"
        self.send(msg, level="info")

    def error_alert(self, error: str, context: str = ""):
        """Alert for errors."""
        msg = f"Error: {error}"
        if context:
            msg += f"\nContext: {context}"
        self.send(msg, level="error")

    def daily_report(self, trades: int, pnl: float, drawdown: float):
        """Send daily summary."""
        msg = f"Daily Report\nTrades: {trades}\nPnL: {pnl:+.2f}\nDrawdown: {drawdown:.2%}"
        level = "warn" if drawdown > 0.15 else "info"
        self.send(msg, level=level)
