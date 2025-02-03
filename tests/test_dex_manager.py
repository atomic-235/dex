"""
Tests for the generalized DEX manager
"""

import os
import pytest
import logging
import asyncio
from web3 import Web3
from dotenv import load_dotenv
from decimal import Decimal

from dex.dex_manager import DEXManager, Token

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


@pytest.fixture
def w3():
    """Create Web3 instance"""
    return Web3(Web3.HTTPProvider(os.getenv('RPC_URL')))


@pytest.fixture
def dex_manager(w3):
    """Create DEX manager instance"""
    return DEXManager(w3, os.getenv('PRIVATE_KEY'))





@pytest.mark.asyncio

async def test_aerodrome_swaps(dex_manager):
    """Test Aerodrome swaps in both directions"""

    # Get initial balances
    initial_usdc = await dex_manager.get_token_balance('USDC')
    initial_btc = await dex_manager.get_token_balance('cbBTC')
    logger.info(f"Initial balances - USDC: ${initial_usdc/1e6:.2f}, cbBTC: {initial_btc/1e8:.8f}")

    # Test USDC -> cbBTC swap
    usdc_amount = Decimal('3.0')
    result = await dex_manager.swap_tokens(
        'USDC',
        'cbBTC',
        usdc_amount,
        dex_name='aerodrome',
        max_slippage=Decimal('0.01')
    )
    assert result['success'], f"Failed to swap USDC->cbBTC: {result.get('error')}"
    logger.info(f"USDC->cbBTC swap successful on Aerodrome: {result['transactionHash']}")

    # Check new balances
    new_btc = await dex_manager.get_token_balance('cbBTC')
    assert new_btc > initial_btc, "cbBTC balance did not increase after swap"
    btc_gained = (new_btc - initial_btc) / Decimal('1e8')
    logger.info(f"Gained {btc_gained:.8f} cbBTC")

    # Test cbBTC -> USDC swap with half of gained amount
    btc_to_swap = btc_gained / Decimal('2')
    result = await dex_manager.swap_tokens(
        'cbBTC',
        'USDC',
        btc_to_swap,
        dex_name='aerodrome',
        max_slippage=Decimal('0.01')
    )
    assert result['success'], f"Failed to swap cbBTC->USDC: {result.get('error')}"
    logger.info(f"cbBTC->USDC swap successful on Aerodrome: {result['transactionHash']}")


@pytest.mark.asyncio

async def test_uniswap_swaps(dex_manager):

    """Test Uniswap swaps in both directions"""

    # Get initial balances
    initial_usdc = await dex_manager.get_token_balance('USDC')
    initial_btc = await dex_manager.get_token_balance('cbBTC')
    logger.info(f"Initial balances - USDC: ${initial_usdc/1e6:.2f}, cbBTC: {initial_btc/1e8:.8f}")

    # Test USDC -> cbBTC swap
    usdc_amount = Decimal('3.0')
    result = await dex_manager.swap_tokens(
        'USDC',
        'cbBTC',
        usdc_amount,
        dex_name='uniswap',
        max_slippage=Decimal('0.01')
    )
    assert result['success'], f"Failed to swap USDC->cbBTC: {result.get('error')}"
    logger.info(f"USDC->cbBTC swap successful on Uniswap: {result['transactionHash']}")

    # Check new balances
    new_btc = await dex_manager.get_token_balance('cbBTC')
    assert new_btc > initial_btc, "cbBTC balance did not increase after swap"
    btc_gained = (new_btc - initial_btc) / Decimal('1e8')
    logger.info(f"Gained {btc_gained:.8f} cbBTC")

    # Test cbBTC -> USDC swap with half of gained amount
    btc_to_swap = btc_gained / Decimal('2')
    result = await dex_manager.swap_tokens(
        'cbBTC',
        'USDC',
        btc_to_swap,
        dex_name='uniswap',
        max_slippage=Decimal('0.01')
    )
    assert result['success'], f"Failed to swap cbBTC->USDC: {result.get('error')}"
    logger.info(f"cbBTC->USDC swap successful on Uniswap: {result['transactionHash']}")


@pytest.mark.asyncio

async def test_best_rate_swaps(dex_manager):

    """Test getting best rate from all DEXes"""

    # Test USDC -> cbBTC with best rate
    usdc_amount = Decimal('3.0')
    result = await dex_manager.get_exchange_rate(
        'USDC',
        'cbBTC',
        usdc_amount
    )
    assert result['success'], f"Failed to get best USDC->cbBTC rate: {result.get('error')}"
    logger.info(f"Best rate from {result['dex']}: 1 BTC = ${float(1/result['rate']):,.2f}")

    # Test cbBTC -> USDC with best rate
    btc_amount = Decimal('0.0001')  # Small amount for testing
    result = await dex_manager.get_exchange_rate(
        'cbBTC',
        'USDC',
        btc_amount
    )
    assert result['success'], f"Failed to get best cbBTC->USDC rate: {result.get('error')}"
    logger.info(f"Best rate from {result['dex']}: 1 BTC = ${float(result['rate']):,.2f}")


@pytest.mark.asyncio

async def test_swap_tokens(dex_manager):

    """Test actual token swaps using DEX manager"""
    # Get initial balances
    initial_usdc = await dex_manager.get_token_balance('USDC')
    initial_btc = await dex_manager.get_token_balance('cbBTC')
    logger.info(f"Initial balances - USDC: ${initial_usdc/1e6:.2f}, cbBTC: {initial_btc/1e8:.8f}")

    # Test USDC -> cbBTC swap
    usdc_amount = Decimal('3.0')
    result = await dex_manager.swap_tokens(
        'USDC',
        'cbBTC',
        usdc_amount,
        max_slippage=Decimal('0.01')
    )
    assert result['success'], f"USDC->cbBTC swap failed: {result.get('error')}"
    logger.info(f"USDC->cbBTC swap successful on {result['dex']}")
    logger.info(f"Transaction hash: {result['transactionHash']}")

    # Check balances after first swap
    mid_usdc = await dex_manager.get_token_balance('USDC')
    mid_btc = await dex_manager.get_token_balance('cbBTC')
    assert mid_btc > initial_btc, "cbBTC balance did not increase after first swap"
    assert mid_usdc < initial_usdc, "USDC balance did not decrease after first swap"
    btc_gained = (mid_btc - initial_btc) / Decimal('1e8')
    logger.info(f"Gained {btc_gained:.8f} cbBTC")

    # Test cbBTC -> USDC swap
    # Swap half of the gained cbBTC back to USDC
    btc_amount = btc_gained / 2
    result = await dex_manager.swap_tokens(
        'cbBTC',
        'USDC',
        btc_amount,
        max_slippage=Decimal('0.01')
    )
    assert result['success'], f"cbBTC->USDC swap failed: {result.get('error')}"
    logger.info(f"cbBTC->USDC swap successful on {result['dex']}")
    logger.info(f"Transaction hash: {result['transactionHash']}")

    # Check final balances
    final_usdc = await dex_manager.get_token_balance('USDC')
    final_btc = await dex_manager.get_token_balance('cbBTC')
    assert final_btc < mid_btc, "cbBTC balance did not decrease after reverse swap"
    assert final_usdc > mid_usdc, "USDC balance did not increase after reverse swap"
    logger.info(f"Final balances - USDC: ${final_usdc/1e6:.2f}, cbBTC: {final_btc/1e8:.8f}")
