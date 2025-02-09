"""
Tests for the generalized DEX manager
"""

import os
import time
import pytest
import logging
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





def test_aerodrome_swaps(dex_manager):
    """Test Aerodrome swaps in both directions"""

    # Get initial balances
    initial_usdc = dex_manager.get_token_balance('USDC')
    initial_btc = dex_manager.get_token_balance('cbBTC')
    logger.info(f"Initial balances - USDC: ${initial_usdc/1e6:.2f}, cbBTC: {initial_btc/1e8:.8f}")

    # Test USDC -> cbBTC swap
    usdc_amount = Decimal('3.0')
    result = dex_manager.swap_tokens(
        'USDC',
        'cbBTC',
        usdc_amount,
        dex_name='aerodrome',
        max_slippage=Decimal('0.01')
    )
    assert result['success'], f"Failed to swap USDC->cbBTC: {result.get('error')}"
    logger.info(f"USDC->cbBTC swap successful on Aerodrome: {result['transactionHash']}")

    # Wait a bit for node to update and check new balances
    time.sleep(2)  # Wait 2 seconds for node to update
    new_btc = dex_manager.get_token_balance('cbBTC')
    assert new_btc > initial_btc, "cbBTC balance did not increase after swap"
    btc_gained = (new_btc - initial_btc) / Decimal('1e8')
    logger.info(f"Gained {btc_gained:.8f} cbBTC")

    # Test cbBTC -> USDC swap (leave some for gas)
    btc_to_swap = int(new_btc * 0.99)  # Leave 1% for gas fees
    result = dex_manager.swap_tokens(
        'cbBTC',
        'USDC',
        btc_to_swap,
        dex_name='aerodrome',
        max_slippage=Decimal('0.01')
    )
    assert result['success'], f"Failed to swap cbBTC->USDC: {result.get('error')}"
    logger.info(f"cbBTC->USDC swap successful on Aerodrome: {result['transactionHash']}")


def test_uniswap_swaps(dex_manager):

    """Test Uniswap swaps in both directions"""

    # Get initial balances
    initial_usdc = dex_manager.get_token_balance('USDC')
    initial_btc = dex_manager.get_token_balance('cbBTC')
    logger.info(f"Initial balances - USDC: ${initial_usdc/1e6:.2f}, cbBTC: {initial_btc/1e8:.8f}")

    # Test USDC -> cbBTC swap
    usdc_amount = Decimal('3.0')
    result = dex_manager.swap_tokens(
        'USDC',
        'cbBTC',
        usdc_amount,
        dex_name='uniswap',
        max_slippage=Decimal('0.01')
    )
    assert result['success'], f"Failed to swap USDC->cbBTC: {result.get('error')}"
    logger.info(f"USDC->cbBTC swap successful on Uniswap: {result['transactionHash']}")

    # Wait a bit for node to update and check new balances
    time.sleep(2)  # Wait 2 seconds for node to update
    new_btc = dex_manager.get_token_balance('cbBTC')
    assert new_btc > initial_btc, "cbBTC balance did not increase after swap"
    btc_gained = (new_btc - initial_btc) / Decimal('1e8')
    logger.info(f"Gained {btc_gained:.8f} cbBTC")

    # Test cbBTC -> USDC swap (leave some for gas)
    btc_to_swap = int(new_btc * 0.99)  # Leave 1% for gas fees
    result = dex_manager.swap_tokens(
        'cbBTC',
        'USDC',
        btc_to_swap,
        dex_name='uniswap',
        max_slippage=Decimal('0.01')
    )
    assert result['success'], f"Failed to swap cbBTC->USDC: {result.get('error')}"
    logger.info(f"cbBTC->USDC swap successful on Uniswap: {result['transactionHash']}")


def test_best_rate_swaps(dex_manager):

    """Test getting best rate from all DEXes"""

    # Test USDC -> cbBTC with best rate
    usdc_amount = Decimal('3.0')
    result = dex_manager.get_exchange_rate(
        'USDC',
        'cbBTC',
        usdc_amount
    )
    assert result['success'], f"Failed to get best USDC->cbBTC rate: {result.get('error')}"
    logger.info(f"Best rate from {result['dex']}: 1 BTC = ${float(1/result['rate']):,.2f}")

    # Test cbBTC -> USDC with best rate
    btc_amount = Decimal('0.0001')  # Small amount for testing
    result = dex_manager.get_exchange_rate(
        'cbBTC',
        'USDC',
        btc_amount
    )
    assert result['success'], f"Failed to get best cbBTC->USDC rate: {result.get('error')}"
    logger.info(f"Best rate from {result['dex']}: 1 BTC = ${float(result['rate']):,.2f}")


def test_eth_balance(dex_manager):
    """Test ETH balance retrieval functionality"""
    # Get ETH balance using Token enum
    eth_balance = dex_manager.get_token_balance('ETH')
    logger.info(f"ETH balance: {eth_balance/1e18:.6f} ETH")

    # Verify the balance is a non-negative number
    assert eth_balance >= 0, "ETH balance should be non-negative"

    # Get ETH balance directly from web3 for comparison
    account = dex_manager.w3.eth.account.from_key(dex_manager.private_key)
    web3_eth_balance = dex_manager.w3.eth.get_balance(account.address)

    # Verify both methods return the same balance
    assert eth_balance == web3_eth_balance, "ETH balance from DEX manager should match web3 balance"


def test_token_balances(dex_manager):
    """Test ERC20 token balance retrieval functionality"""
    # Test USDC balance
    usdc_balance = dex_manager.get_token_balance('USDC')
    logger.info(f"USDC balance: ${usdc_balance/1e6:.2f}")
    assert usdc_balance >= 0, "USDC balance should be non-negative"

    # Test cbBTC balance
    cbbtc_balance = dex_manager.get_token_balance('cbBTC')
    logger.info(f"cbBTC balance: {cbbtc_balance/1e8:.8f} BTC")
    assert cbbtc_balance >= 0, "cbBTC balance should be non-negative"

    # Verify balances using direct contract calls
    account = dex_manager.w3.eth.account.from_key(dex_manager.private_key)
    
    # Get USDC balance via contract
    usdc_contract = dex_manager.w3.eth.contract(
        address=dex_manager._get_token_address('USDC'),
        abi=next(iter(dex_manager.dexes.values())).token_abi
    )
    contract_usdc_balance = usdc_contract.functions.balanceOf(account.address).call()
    assert usdc_balance == contract_usdc_balance, "USDC balance from DEX manager should match contract balance"

    # Get cbBTC balance via contract
    cbbtc_contract = dex_manager.w3.eth.contract(
        address=dex_manager._get_token_address('cbBTC'),
        abi=next(iter(dex_manager.dexes.values())).token_abi
    )
    contract_cbbtc_balance = cbbtc_contract.functions.balanceOf(account.address).call()
    assert cbbtc_balance == contract_cbbtc_balance, "cbBTC balance from DEX manager should match contract balance"


def test_swap_tokens(dex_manager):

    """Test actual token swaps using DEX manager"""
    # Get initial balances
    initial_usdc = dex_manager.get_token_balance('USDC')
    initial_btc = dex_manager.get_token_balance('cbBTC')
    logger.info(f"Initial balances - USDC: ${initial_usdc/1e6:.2f}, cbBTC: {initial_btc/1e8:.8f}")

    # Test USDC -> cbBTC swap
    usdc_amount = Decimal('3.0')
    result = dex_manager.swap_tokens(
        'USDC',
        'cbBTC',
        usdc_amount,
        max_slippage=Decimal('0.01')
    )
    assert result['success'], f"USDC->cbBTC swap failed: {result.get('error')}"
    logger.info(f"USDC->cbBTC swap successful on {result['dex']}")
    logger.info(f"Transaction hash: {result['transactionHash']}")

    # Wait a bit for node to update and check balances after first swap
    time.sleep(2)  # Wait 2 seconds for node to update
    mid_usdc = dex_manager.get_token_balance('USDC')
    mid_btc = dex_manager.get_token_balance('cbBTC')
    assert mid_btc > initial_btc, "cbBTC balance did not increase after first swap"
    assert mid_usdc < initial_usdc, "USDC balance did not decrease after first swap"
    btc_gained = (mid_btc - initial_btc) / Decimal('1e8')
    logger.info(f"Gained {btc_gained:.8f} cbBTC")

    # Test cbBTC -> USDC swap (leave some for gas)
    btc_amount = int(mid_btc * 0.99)  # Leave 1% for gas fees
    result = dex_manager.swap_tokens(
        'cbBTC',
        'USDC',
        btc_amount,
        max_slippage=Decimal('0.01')
    )
    assert result['success'], f"cbBTC->USDC swap failed: {result.get('error')}"
    logger.info(f"cbBTC->USDC swap successful on {result['dex']}")
    logger.info(f"Transaction hash: {result['transactionHash']}")

    # Wait a bit for node to update and check final balances
    time.sleep(2)  # Wait 2 seconds for node to update
    final_usdc = dex_manager.get_token_balance('USDC')
    final_btc = dex_manager.get_token_balance('cbBTC')
    assert final_btc < mid_btc, "cbBTC balance did not decrease after reverse swap"
    assert final_usdc > mid_usdc, "USDC balance did not increase after reverse swap"
    logger.info(f"Final balances - USDC: ${final_usdc/1e6:.2f}, cbBTC: {final_btc/1e8:.8f}")
