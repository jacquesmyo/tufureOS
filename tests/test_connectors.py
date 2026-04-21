"""Unit tests for market connectors."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from connectors.polymarket import PolymarketConnector
from connectors.binance import BinanceConnector


class TestPolymarketConnector:
    def test_format_market(self):
        c = PolymarketConnector()
        sample = {
            "slug": "test-market",
            "question": "Will it rain?",
            "active": True,
            "closed": False,
            "outcomes": "[{\"price\": 0.55}]",
        }
        result = c.format_market(sample)
        assert result is not None
        assert result["slug"] == "test-market"
        assert result["price"] == 0.55

    def test_format_closed_market(self):
        c = PolymarketConnector()
        sample = {"active": True, "closed": True}
        assert c.format_market(sample) is None


class TestBinanceConnector:
    def test_get_price_mock(self):
        # This may fail in CI without network; mark accordingly
        c = BinanceConnector()
        # Just test that the method exists and has correct signature
        assert hasattr(c, "get_price")
        assert hasattr(c, "get_klines")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
