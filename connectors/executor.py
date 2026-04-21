"""
Real order execution module for Polymarket CLOB.
Handles order signing, placement, and fill tracking.
"""
import os
import time
from typing import Optional
from decimal import Decimal

from src.events import EventEmitter, EventKind

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds, MarketOrderArgs, OrderType
    CLOB_AVAILABLE = True
except ImportError:
    CLOB_AVAILABLE = False


class ExecutionError(Exception):
    """Raised when order execution fails."""
    pass


class PolymarketExecutor:
    """Executes real orders on Polymarket CLOB."""

    def __init__(
        self,
        emitter: EventEmitter,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        passphrase: Optional[str] = None,
        private_key: Optional[str] = None,
        chain_id: int = 137,
    ):
        self.emitter = emitter
        self.api_key = api_key or os.getenv("POLYMARKET_API_KEY")
        self.api_secret = api_secret or os.getenv("POLYMARKET_SECRET")
        self.passphrase = passphrase or os.getenv("POLYMARKET_PASSPHRASE")
        self.private_key = private_key or os.getenv("POLYMARKET_PRIVATE_KEY")
        self.chain_id = chain_id
        self.client: Optional[ClobClient] = None
        self._init_client()

    def _init_client(self):
        if not CLOB_AVAILABLE:
            self.emitter.emit(EventKind.API_ERROR, provider="polymarket", error="py_clob_client not installed")
            return
        if not all([self.api_key, self.api_secret, self.passphrase, self.private_key]):
            self.emitter.emit(EventKind.API_ERROR, provider="polymarket", error="Missing API credentials")
            return

        try:
            self.client = ClobClient(
                host="https://clob.polymarket.com",
                key=self.private_key,
                chain_id=self.chain_id,
                creds=ApiCreds(
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                    api_passphrase=self.passphrase,
                ),
            )
            self.emitter.emit(EventKind.API_RESPONSE, provider="polymarket", action="init")
        except Exception as e:
            self.emitter.emit(EventKind.API_ERROR, provider="polymarket", error=str(e))

    def place_market_order(
        self,
        token_id: str,
        side: str,  # "BUY" or "SELL"
        size: float,
    ) -> dict:
        """Place a market order on Polymarket."""
        if not self.client:
            raise ExecutionError("CLOB client not initialized")

        if side not in ("BUY", "SELL"):
            raise ExecutionError(f"Invalid side: {side}")

        self.emitter.emit(
            EventKind.ORDER_PLACED,
            market=token_id,
            action=side,
            size=size,
            order_type="market",
            paper=False,
        )

        try:
            order_args = MarketOrderArgs(
                token_id=token_id,
                amount=size,
                side=side,
            )
            order = self.client.create_market_order(order_args)
            resp = self.client.post_order(order, orderType=OrderType.FOK)

            self.emitter.emit(
                EventKind.ORDER_FILLED,
                market=token_id,
                action=side,
                size=size,
                response=resp,
            )
            return resp

        except Exception as e:
            self.emitter.emit(EventKind.ORDER_FAILED, market=token_id, error=str(e))
            raise ExecutionError(f"Order failed: {e}")

    def get_balance(self) -> dict:
        """Get USDC balance and positions."""
        if not self.client:
            return {"usdc": 0.0, "positions": []}
        try:
            balance = self.client.get_balance()
            positions = self.client.get_positions()
            return {"usdc": balance, "positions": positions}
        except Exception as e:
            self.emitter.emit(EventKind.API_ERROR, provider="polymarket", error=str(e))
            return {"usdc": 0.0, "positions": [], "error": str(e)}

    def cancel_all(self):
        """Cancel all open orders."""
        if not self.client:
            return
        try:
            self.client.cancel_all()
            self.emitter.emit(EventKind.ORDER_CANCELLED, action="cancel_all")
        except Exception as e:
            self.emitter.emit(EventKind.API_ERROR, provider="polymarket", error=str(e))
