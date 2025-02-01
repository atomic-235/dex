from web3 import Web3
from datetime import datetime
from typing import List, Dict, Optional
import asyncio
import logging
from .base import BaseDEX
from .config import ABASUSDC_ADDRESS, load_abi
from decimal import Decimal

logger = logging.getLogger(__name__)


class InterestCalculator:
    """Aave interest calculator for Base network"""

    def __init__(self, w3: Web3, wallet_address: Optional[str] = None):
        """Initialize Aave interest calculator
        Args:
            w3: Web3 instance
            wallet_address: Optional wallet address to calculate interest for. If not provided,
                          will use the address from the Aave instance.
        """
        self.w3 = w3
        self.wallet_address = wallet_address
        logger.info(f"Initializing Aave interest calculator for {wallet_address if wallet_address else 'default address'} "
                   f"on {self.w3.provider.endpoint_uri}")
        
        # Load ABI for aToken contract
        self.atoken_abi = load_abi('atoken.json')
        
        self.abasusdc_contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(ABASUSDC_ADDRESS),
            abi=self.atoken_abi
        )
        
        # Verify contract and get decimals
        try:
            self.decimals = self.abasusdc_contract.functions.decimals().call()
            underlying = self.abasusdc_contract.functions.UNDERLYING_ASSET_ADDRESS().call()
            logger.info(f"Connected to aBasUSDC contract. Decimals: {self.decimals}, Underlying: {underlying}")
        except Exception as e:
            logger.error(f"Error verifying contract: {e}")


    def get_balance_at_block(self, block_number: int, address: Optional[str] = None) -> float:
        """Get aToken balance at specific block number
        Args:
            block_number: Block number to check balance at
            address: Optional address to check balance for. If not provided, uses the default address
        """
        try:
            target_address = address or self.wallet_address
            if not target_address:
                raise ValueError("No address provided and no default address set")

            # First verify the block exists
            try:
                block = self.w3.eth.get_block(block_number)
                logger.info(f"Checking balance for {target_address} at block {block_number} "
                           f"(timestamp: {datetime.fromtimestamp(block['timestamp'])})")
            except Exception as e:
                logger.error(f"Error accessing block {block_number}: {e}")
                return 0

            balance = self.abasusdc_contract.functions.balanceOf(target_address).call(
                block_identifier=block_number
            )
            balance_usdc = float(balance) / (10 ** self.decimals)
            logger.info(f"Balance at block {block_number}: {balance_usdc:.2f} USDC")
            return balance_usdc
        except Exception as e:
            logger.error(f"Error getting balance at block {block_number}: {e}")
            return 0

    def calculate_interest(self, start_block: int, end_block: int, address: Optional[str] = None) -> Dict:
        """
        Calculate interest earned by comparing transfer history with actual balance
        and by summing up interest accrual events
        """
        # Get all transfers
        target_address = address or self.wallet_address
        if not target_address:
            logger.error("No address provided and no default address set; returning zeros")
            return {
                "expected_balance": 0,
                "actual_balance": 0,
                "interest_earned": 0,
                "interest_from_events": 0,
                "transactions": [],
                "start_block": start_block,
                "end_block": end_block
            }
            
        transactions = self.track_deposits_withdrawals(start_block, end_block, target_address)
        
        # Calculate expected balance based on transfers
        expected_balance = 0
        for tx in transactions:
            expected_balance += tx['amount']
        
        logger.info(f"Expected balance based on transfers: {expected_balance:.2f} USDC")
        
        # Get actual current balance
        actual_balance = self.get_balance_at_block(end_block, target_address)
        logger.info(f"Actual balance: {actual_balance:.2f} USDC")
        
        # Interest is the difference between actual and expected balance
        interest_earned = actual_balance - expected_balance
        
        # Calculate interest by summing up interest accrual events
        logger.info("Calculating interest from accrual events...")
        interest_events = self.abasusdc_contract.events.Transfer.get_logs(
            from_block=start_block,
            to_block=end_block,
            argument_filters={
                'from': '0x0000000000000000000000000000000000000000',
                'to': target_address
            }
        )
        total_interest_from_events = sum(float(e['args']['value']) / (10 ** self.decimals) for e in interest_events)
        logger.info(f"Found {len(interest_events)} interest accrual events")
        logger.info(f"Total interest from events: {total_interest_from_events:.2f} USDC")
        
        return {
            "expected_balance": expected_balance,
            "actual_balance": actual_balance,
            "interest_earned": interest_earned,
            "interest_from_events": total_interest_from_events,
            "transactions": transactions,
            "start_block": start_block,
            "end_block": end_block
        }

    def track_deposits_withdrawals(self, start_block: int, end_block: int, address: Optional[str] = None) -> List[Dict]:
        """
        Track deposits and withdrawals between blocks by monitoring Transfer events
        Returns list of transactions with their details
        """
        logger.info(f"Tracking transactions from block {start_block} to {end_block}...")
        
        # Get Transfer events for deposits and withdrawals
        events = []
        
        # Get deposits (transfers to our address)
        deposit_events = self.abasusdc_contract.events.Transfer.get_logs(
            from_block=start_block,
            to_block=end_block,
            argument_filters={'to': address or self.wallet_address}
        )
        events.extend(deposit_events)
        
        # Get withdrawals (transfers from our address)
        withdrawal_events = self.abasusdc_contract.events.Transfer.get_logs(
            from_block=start_block,
            to_block=end_block,
            argument_filters={'from': address or self.wallet_address}
        )
        events.extend(withdrawal_events)
        transactions = []
        
        for event in events:
            # Skip interest accrual transfers (from zero address)
            if event['args']['from'] == '0x0000000000000000000000000000000000000000':
                continue
                
            tx_hash = event['transactionHash'].hex()
            block_number = event['blockNumber']
            block = self.w3.eth.get_block(block_number)
            timestamp = datetime.fromtimestamp(block['timestamp'])
            
            amount = float(event['args']['value']) / (10 ** self.decimals)
            target_address = address or self.wallet_address
            is_deposit = event['args']['to'].lower() == target_address.lower()
            
            logger.debug(f"Analyzing transaction {tx_hash}:")
            logger.debug(f"From: {event['args']['from']}")
            logger.debug(f"To: {event['args']['to']}")
            logger.debug(f"Raw Amount: {event['args']['value']}")
            logger.debug(f"Decimals: {self.decimals}")
            logger.debug(f"Calculated Amount: {amount}")
            
            tx_info = {
                'timestamp': timestamp,
                'block': block_number,
                'type': 'deposit' if is_deposit else 'withdrawal',
                'amount': amount if is_deposit else -amount,
                'tx_hash': tx_hash,
                'from': event['args']['from'],
                'to': event['args']['to']
            }
            transactions.append(tx_info)
            
        return sorted(transactions, key=lambda x: x['block'])

    def calculate_apy(self, interest_earned: Decimal, principal: Decimal, days: Decimal) -> Decimal:
        """Calculate annualized interest rate"""
        if principal == 0 or days == 0:
            return Decimal('0')
        # Calculate the daily rate by dividing total return by number of days
        daily_rate = (interest_earned / principal) / days
        # Annualize by compounding daily rate for 365 days
        apy = ((1 + daily_rate) ** 365) - 1
        return apy


class Aave(BaseDEX):
    """Aave protocol implementation"""

    def __init__(self, w3: Web3, private_key: str):
        """Initialize Aave"""
        super().__init__(w3, private_key)
        self.wallet_address = Web3.to_checksum_address(w3.eth.account.from_key(private_key).address)
        logger.info(f"Initializing Aave with wallet {self.wallet_address}")
        self.interest = InterestCalculator(w3, self.wallet_address)
        
    def get_interest_for_address(self, address: str) -> InterestCalculator:
        """Get interest calculator for a specific address"""
        return InterestCalculator(self.w3, Web3.to_checksum_address(address))
