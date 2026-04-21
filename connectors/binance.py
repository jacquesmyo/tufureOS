"""
Real Binance connector for spot market data.
Uses public API for data, requires keys for trading.
"""
import json
import os
import time
import hmac
import hashlib
from typing import Optional, List, Dict
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode


class BinanceConnector:
    """Binance spot connector."""

    BASE = "https://api.binance.com"
    TESTNET = "https://testnet.binance.vision"

    def __init__(self, api_key: Optional[str] = None, secret: Optional[str] = None, testnet: bool = False):
        self.api_key = api_key or os.getenv("BINANCE_API_KEY", "")
        self.secret = secret or os.getenv("BINANCE_SECRET", "")
        self.base = self.TESTNET if testnet else self.BASE
        self.headers = {"X-MBX-APIKEY": self.api_key} if self.api_key else {}

    def _get(self, endpoint: str, params: Optional[dict] = None, signed: bool = False) -> dict:
        url = f"{self.base}{endpoint}"
        if params:
            if signed and self.secret:
                params["timestamp"] = int(time.time() * 1000)
                query = urlencode(params)
                signature = hmac.new(self.secret.encode(), query.encode(), hashlib.sha256).hexdigest()
                query += f"&signature={signature}"
                url += "?" + query
            else:
                url += "?" + urlencode(params)

        req = Request(url, headers=self.headers)
        try:
            with urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            err = json.loads(e.read().decode()) if e.read() else {}
            raise RuntimeError(f"Binance API error: {err.get('msg', e.reason)}")

    def get_price(self, symbol: str = "BTCUSDT") -> float:
        """Get current price."""
        data = self._get("/api/v3/ticker/price", {"symbol": symbol})
        return float(data.get("price", 0))

    def get_orderbook(self, symbol: str = "BTCUSDT", limit: int = 5) -> dict:
        """Get order book."""
        return self._get("/api/v3/depth", {"symbol": symbol, "limit": limit})

    def get_klines(self, symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 100) -> List[List]:
        """Get candlestick data. Returns list of [open_time, open, high, low, close, volume, ...]."""
        return self._get("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})

    def get_ticker_24h(self, symbol: str = "BTCUSDT") -> dict:
        """Get 24h stats."""
        return self._get("/api/v3/ticker/24hr", {"symbol": symbol})

    def get_account(self) -> dict:
        """Get account info (requires API key)."""
        return self._get("/api/v3/account", signed=True)

    def place_order(self, symbol: str, side: str, quantity: float, order_type: str = "MARKET") -> dict:
        """Place an order (requires API key + secret)."""
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": quantity,
        }
        return self._get("/api/v3/order", params, signed=True)
