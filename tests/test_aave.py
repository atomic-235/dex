"""
Tests for Aave interest calculations
"""

import os
import pytest
import logging
from web3 import Web3
from dotenv import load_dotenv
from decimal import Decimal
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

from dex.aave import Aave
from dex.config import ABASUSDC_ADDRESS

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Constants
USDC_DECIMALS = 6


@dataclass
class InterestTestCase:
    """Test case for interest calculation"""
    name: str
    blocks_back: int
    address: str  # Address to calculate interest for
    expected_min_interest: Decimal  # Minimum expected interest rate (annualized)
    expected_max_interest: Decimal  # Maximum expected interest rate (annualized)


# Test cases
def test_calculate_interest(aave: Aave):
    """Test interest calculation for current address"""
    current_block = aave.w3.eth.block_number
    # Test last 24h
    interest_24h = aave.interest.calculate_interest(
        start_block=current_block - 7200,  # ~24h worth of blocks
        end_block=current_block
    )
    
    # Test last 7d
    interest_7d = aave.interest.calculate_interest(
        start_block=current_block - 50400,  # ~7d worth of blocks
        end_block=current_block
    )
    
    # Verify the data structure
    for interest_data in [interest_24h, interest_7d]:
        assert 'expected_balance' in interest_data
        assert 'actual_balance' in interest_data
        assert 'interest_earned' in interest_data
        assert 'interest_from_events' in interest_data
        assert 'transactions' in interest_data
        
        # Verify calculations match
        assert abs(interest_data['interest_earned'] - interest_data['interest_from_events']) < 0.01, \
            'Interest calculations from balance diff and events should match'
            
        # Verify balances make sense
        assert interest_data['actual_balance'] >= 0, 'Balance should not be negative'
        assert interest_data['expected_balance'] >= 0, 'Expected balance should not be negative'
        
        # Verify transactions list structure
        for tx in interest_data['transactions']:
            assert 'timestamp' in tx
            assert 'block' in tx
            assert 'type' in tx
            assert 'amount' in tx
            assert 'tx_hash' in tx
            assert tx['type'] in ['deposit', 'withdrawal']


def test_interest_for_other_address(aave: Aave):
    """Test interest calculation for another address"""
    # Use a known active address
    test_address = "0x5723DB3c8a4586D33353143B2B785b74e283E7C4"
    current_block = aave.w3.eth.block_number
    
    interest_data = aave.interest.calculate_interest(
        start_block=current_block - 7200,
        end_block=current_block,
        address=test_address
    )
    
    # Verify we got data for the correct address
    for tx in interest_data['transactions']:
        if tx['type'] == 'deposit':
            assert tx['to'] == test_address
        else:  # withdrawal
            assert tx['from'] == test_address


@pytest.fixture
def w3():
    """Create Web3 instance"""
    rpc_url = os.getenv('RPC_URL', 'https://mainnet.base.org')  # Default to Base mainnet
    logger.info(f"Using RPC URL: {rpc_url}")
    
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        raise ConnectionError("Failed to connect to Base network")
    
    return w3


@pytest.fixture
def aave(w3):
    """Create Aave instance"""
    private_key = os.getenv('PRIVATE_KEY')
    if not private_key:
        raise ValueError("PRIVATE_KEY environment variable not set")
    
    return Aave(w3, private_key)


def calculate_apy(interest_earned: Decimal, principal: Decimal, days: Decimal) -> Decimal:
    """Calculate annualized interest rate"""
    if principal == 0 or days == 0:
        return Decimal('0')
    # Calculate the daily rate by dividing total return by number of days
    daily_rate = (interest_earned / principal) / days
    # Annualize by compounding daily rate for 365 days
    apy = ((1 + daily_rate) ** 365) - 1
    return apy


def test_calculate_interest_all_time(aave: Aave):
    """Test interest calculation from first deposit to current block"""
    # Get all transactions for test address
    test_address = "0x5723DB3c8a4586D33353143B2B785b74e283E7C4"
    interest_calc = aave.get_interest_for_address(test_address)
    
    # Get first deposit block
    all_txs = interest_calc.track_deposits_withdrawals(0, 'latest')
    deposits = [tx for tx in all_txs if tx['type'] == 'deposit']
    
    if not deposits:
        pytest.fail("No deposit transactions found for test address")
    
    first_deposit = min(deposits, key=lambda x: x['block'])
    start_block = first_deposit['block']
    
    # Get timestamps for duration calculation
    start_block_data = aave.w3.eth.get_block(start_block)
    current_block = aave.w3.eth.block_number
    current_block_data = aave.w3.eth.get_block(current_block)
    
    # Calculate duration in days
    days = Decimal(str((current_block_data['timestamp'] - start_block_data['timestamp']) / 86400))

    # Calculate interest from first deposit to now
    interest_data = interest_calc.calculate_interest(start_block, current_block)

    principal = Decimal(str(interest_data['expected_balance']))
    interest_earned = Decimal(str(interest_data['interest_earned']))

    apy = interest_calc.calculate_apy(interest_earned, principal, days)

    logger.info(f"All-time Interest Calculation:")
    logger.info(f"First deposit block: {start_block}")
    logger.info(f"Principal: {principal} USDC")
    logger.info(f"Interest earned: {interest_earned} USDC")
    logger.info(f"Duration (days): {days}")
    logger.info(f"APY: {apy * 100}%")

    interest_from_events = Decimal(str(interest_data['interest_from_events']))
    assert abs(interest_earned - interest_from_events) < Decimal('6'), \
        f"Interest calculation mismatch: {interest_earned} vs {interest_from_events}"
