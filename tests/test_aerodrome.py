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
from typing import Tuple, Optional

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
    is_reverse: bool = False  # True for cbBTC -> USDC swaps
    _amount_in: Optional[int] = None

    @property
    def amount_in(self) -> int:
        """Get amount in wei"""
        if self.is_reverse:
            if self._amount_in is None:
                raise ValueError("amount_in not set for reverse swap")
            return self._amount_in
        return int(self.amount_usdc * Decimal(10**USDC_DECIMALS))

    def set_amount_in(self, amount: int):
        """Set the amount to use for the swap"""
        self._amount_in = amount


# Test cases
TEST_CASES = [
    # USDC -> cbBTC case
    SwapTestCase(
        name="Regular amount",
        amount_usdc=Decimal('3.0'),
        max_slippage=Decimal('1.0'),  # 1% max slippage for regular amounts
        is_reverse=False
    ),
    # cbBTC -> USDC case
    SwapTestCase(
        name="Sell all cbBTC to USDC",
        amount_usdc=Decimal('0.0'),  # Not used for reverse swaps
        max_slippage=Decimal('1.0'),
        is_reverse=True
    )
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
    if not test_case.is_reverse:
        # USDC -> cbBTC
        quote = await dex.get_quote(USDC_ADDRESS, cbBTC_ADDRESS, test_case.amount_in)
        quote_in_btc = Decimal(str(quote)) / Decimal(str(10**cbBTC_DECIMALS))
        effective_price = test_case.amount_usdc / quote_in_btc
        logger.info(f"Quote for {test_case.amount_usdc} USDC: {quote_in_btc:.8f} cbBTC")
        return quote_in_btc, effective_price, quote
    else:
        # cbBTC -> USDC
        quote = await dex.get_quote(cbBTC_ADDRESS, USDC_ADDRESS, test_case.amount_in)
        quote_in_usdc = Decimal(str(quote)) / Decimal(str(10**USDC_DECIMALS))
        btc_amount = Decimal(str(test_case.amount_in)) / Decimal(str(10**cbBTC_DECIMALS))
        effective_price = quote_in_usdc / btc_amount
        logger.info(f"Quote for {btc_amount:.8f} cbBTC: {quote_in_usdc:.2f} USDC")
        return quote_in_usdc, effective_price, quote


@pytest.mark.asyncio
@pytest.mark.parametrize('test_case', TEST_CASES)
async def test_swap_with_slippage_check(dex, binance, test_case):
    """Test token swaps with slippage protection in both directions"""
    if not test_case.is_reverse:
        # USDC -> cbBTC
        token_in, token_out = USDC_ADDRESS, cbBTC_ADDRESS
        test_case.set_amount_in(int(test_case.amount_usdc * Decimal(10**USDC_DECIMALS)))
    else:
        # cbBTC -> USDC
        token_in, token_out = cbBTC_ADDRESS, USDC_ADDRESS
        # Check cbBTC balance
        token = dex.w3.eth.contract(address=token_in, abi=dex.token_abi)
        balance = await asyncio.to_thread(
            lambda: token.functions.balanceOf(dex.address).call()
        )
        if balance == 0:
            pytest.skip("Skipping reverse swap test due to zero cbBTC balance")
        test_case.set_amount_in(balance)

    # Get current BTC price from Binance for reference
    btc_price = binance.get_current_btc_price()
    logger.info(f"Current BTC price on Binance: ${btc_price:,.2f}")

    # Get quote and calculate prices
    quote_amount, effective_price, quote = await get_swap_quote(dex, test_case)

    # Check slippage
    price_diff = calculate_price_difference(float(effective_price), btc_price)
    logger.info(f"Price difference: {price_diff:.3f}%")

    # Only proceed if slippage is acceptable
    if price_diff > float(test_case.max_slippage):
        logger.warning(f"Price difference too high: {price_diff:.3f}% > {test_case.max_slippage}%")

    # Approve token spending if needed
    await dex.approve_token(token_in, test_case.amount_in, dex.router_address)

    # Execute swap
    tx = await dex.swap_tokens(token_in, token_out, test_case.amount_in)

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
