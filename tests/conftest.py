import pytest
import requests

class BinanceDataProvider:
    """Binance data provider for testing"""
    def __init__(self):
        self.base_url = "https://api.binance.com/api/v3"

    def get_current_btc_price(self) -> float:
        """Get current BTC price in USDC"""
        response = requests.get(f"{self.base_url}/ticker/price", params={"symbol": "BTCUSDC"})
        if response.status_code == 200:
            return float(response.json()["price"])
        raise Exception("Failed to get BTC price from Binance")

@pytest.fixture
def binance():
    """Create BinanceDataProvider instance"""
    return BinanceDataProvider()
