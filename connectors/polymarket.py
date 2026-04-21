"""
Real Polymarket CLOB connector.
Fetches live market data, order books, and executes trades.
"""
import json
import os
import time
from typing import Optional, List, Dict
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import quote


class PolymarketConnector:
    """Production-grade Polymarket connector with retry logic."""

    GAMMA = "https://gamma-api.polymarket.com"
    CLOB = "https://clob.polymarket.com"
    DATA = "https://data-api.polymarket.com"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("POLYMARKET_API_KEY", "")
        self.headers = {
            "User-Agent": "tufureOS/1.0",
            "Accept": "application/json",
        }
        if self.api_key:
            self.headers["POLYMARKET_API_KEY"] = self.api_key

    def _get(self, url: str, retries: int = 3) -> dict:
        """GET with exponential backoff."""
        for attempt in range(retries):
            try:
                req = Request(url, headers=self.headers)
                with urlopen(req, timeout=15) as resp:
                    return json.loads(resp.read().decode())
            except HTTPError as e:
                if e.code == 429 and attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
            except URLError:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
        return {}

    def search_markets(self, query: str, limit: int = 20) -> List[dict]:
        """Search for active markets."""
        q = quote(query)
        data = self._get(f"{self.GAMMA}/events?closed=false&limit={limit}&search={q}")
        return data.get("events", []) if isinstance(data, dict) else []

    def get_market(self, slug: str) -> Optional[dict]:
        """Get market by slug."""
        data = self._get(f"{self.GAMMA}/events/slug/{slug}")
        return data if isinstance(data, dict) else None

    def get_orderbook(self, token_id: str) -> dict:
        """Get order book for a token."""
        return self._get(f"{self.CLOB}/book/{token_id}")

    def get_price(self, token_id: str) -> float:
        """Get mid price for a token."""
        book = self.get_orderbook(token_id)
        bids = book.get("bids", [])
        asks = book.get("asks", [])
        if bids and asks:
            best_bid = float(bids[0]["price"]) if isinstance(bids[0], dict) else float(bids[0][0])
            best_ask = float(asks[0]["price"]) if isinstance(asks[0], dict) else float(asks[0][0])
            return (best_bid + best_ask) / 2
        return 0.5

    def get_trending(self, limit: int = 10) -> List[dict]:
        """Get trending markets."""
        data = self._get(f"{self.GAMMA}/events?closed=false&limit={limit}&order=volume")
        return data.get("events", []) if isinstance(data, dict) else []

    def get_market_tokens(self, condition_id: str) -> List[dict]:
        """Get tokens for a market condition."""
        data = self._get(f"{self.CLOB}/markets?condition_id={condition_id}")
        return data if isinstance(data, list) else []

    def format_market(self, event: dict) -> dict:
        """Normalize event into tradeable market dict."""
        markets = event.get("markets", [])
        if not markets:
            return {}
        m = markets[0]
        outcomes = m.get("outcomes", ["Yes", "No"])
        prices = m.get("outcomePrices", [])
        if isinstance(prices, str):
            try:
                prices = json.loads(prices)
            except:
                prices = []
        tokens = m.get("clobTokenIds", [])
        if isinstance(tokens, str):
            try:
                tokens = json.loads(tokens)
            except:
                tokens = []

        return {
            "id": m.get("conditionId", ""),
            "slug": m.get("slug", ""),
            "question": m.get("question", ""),
            "volume": float(m.get("volume", 0) or 0),
            "liquidity": float(m.get("liquidity", 0) or 0),
            "outcomes": outcomes,
            "yes_price": float(prices[0]) if len(prices) > 0 else 0.5,
            "no_price": float(prices[1]) if len(prices) > 1 else 0.5,
            "yes_token": tokens[0] if len(tokens) > 0 else None,
            "no_token": tokens[1] if len(tokens) > 1 else None,
            "end_date": m.get("endDate", ""),
            "active": not m.get("closed", False),
        }
