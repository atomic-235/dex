"""
Tests for Aerodrome DEX interactions with slippage checks
"""

import os
import pytest
import logging
from web3 import Web3
from dotenv import load_dotenv
from decimal import Decimal
import asyncio
from dataclasses import dataclass
from typing import Tuple

from dex.aerodrome import AerodromeDEX
from dex.config import USDC_ADDRESS, cbBTC_ADDRESS

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Constants
USDC_DECIMALS = 6
cbBTC_DECIMALS = 8


@dataclass
class SwapTestCase:
    """Test case for token swap"""
    name: str
    amount_usdc: Decimal
    max_slippage: Decimal

    @property
    def amount_in(self) -> int:
        """Convert USDC amount to wei"""
        return int(self.amount_usdc * Decimal(10**USDC_DECIMALS))


# Test cases
TEST_CASES = [
    SwapTestCase(
        name="Regular amount",
        amount_usdc=Decimal('3.0'),
        max_slippage=Decimal('.0')  # 0.65% max slippage for regular amounts
    ),
  
]


@pytest.fixture
def w3():
    """Create Web3 instance"""
    return Web3(Web3.HTTPProvider(os.getenv('RPC_URL')))


@pytest.fixture
def dex(w3):
    """Create AerodromeDEX instance"""
    return AerodromeDEX(w3, os.getenv('PRIVATE_KEY'))


def calculate_price_difference(price1: float, price2: float) -> float:
    """Calculate percentage difference between two prices"""
    return abs(price1 - price2) / price2 * 100


async def get_swap_quote(dex: AerodromeDEX, test_case: SwapTestCase) -> Tuple[Decimal, Decimal, float]:
    """Get swap quote and calculate prices"""
    quote = await dex.get_quote(USDC_ADDRESS, cbBTC_ADDRESS, test_case.amount_in)
    assert isinstance(quote, (int, float))
    assert quote > 0

    # Calculate the effective price (USDC per BTC)
    quote_in_btc = Decimal(str(quote)) / Decimal(str(10**cbBTC_DECIMALS))
    effective_price = test_case.amount_usdc / quote_in_btc

    logger.info(f"Quote for {test_case.amount_usdc} USDC: {quote_in_btc:.8f} cbBTC")
    logger.info(f"Effective price on Aerodrome: ${float(effective_price):,.2f}")

    return quote_in_btc, effective_price, quote


@pytest.mark.asyncio
@pytest.mark.parametrize('test_case', TEST_CASES)
async def test_swap_with_slippage_check(dex, binance, test_case):
    """Test swapping USDC to cbBTC with slippage protection"""
    # Get current BTC price from Binance for reference
    btc_price = binance.get_current_btc_price()
    logger.info(f"Current BTC price on Binance: ${btc_price:,.2f}")

    # Get quote and calculate prices
    quote_in_btc, effective_price, quote = await get_swap_quote(dex, test_case)

    # Check slippage
    price_diff = calculate_price_difference(float(effective_price), btc_price)
    logger.info(f"Price difference: {price_diff:.3f}%")

    # Only proceed if slippage is acceptable
    if price_diff <= float(test_case.max_slippage):
        logger.warning(f"Price difference too high: {price_diff:.3f}% > {test_case.max_slippage}%"
    )

    # Approve USDC spending if needed
    await dex.approve_token(USDC_ADDRESS, test_case.amount_in, dex.router_address)

    # Execute swap
    tx = await dex.swap_tokens(USDC_ADDRESS, cbBTC_ADDRESS, test_case.amount_in)

    assert tx is not None
    assert 'transactionHash' in tx
    assert isinstance(tx['transactionHash'], str)
    assert 'blockNumber' in tx

    tx_hash = tx['transactionHash']
    logger.info(f"Transaction hash: {tx_hash}")
    logger.info(f"View on Basescan: https://basescan.org/tx/{tx_hash}")

    # Wait for transaction confirmation
    receipt = await asyncio.to_thread(
        lambda: dex.w3.eth.wait_for_transaction_receipt(tx_hash)
    )
    assert receipt['status'] == 1  # Transaction successful
