"""
Base DEX implementation.
"""

import asyncio
import logging
from web3 import Web3
from eth_account.datastructures import SignedTransaction
from typing import Dict, Any, Optional, Union, Tuple
from .error_constants import get_readable_error
import threading

logger = logging.getLogger(__name__)


class BaseDEX:
    """Base DEX implementation"""

    def __init__(self, w3: Web3, private_key: str):
        """Initialize base DEX"""
        self.w3 = w3
        self.account = self.w3.eth.account.from_key(private_key)
        self.address = self.account.address
        self.token_abi = None
        self.router = None
        self.slippage = 0.006  # 0.6% slippage tolerance
        self.nonce_lock = threading.Lock()
        self._next_nonce = w3.eth.get_transaction_count(self.address, 'pending')
        
    def _handle_error(self, error: Union[Exception, Tuple[str, str]], context: str) -> Dict[str, Any]:
        """Handle errors in a consistent way across all DEX implementations"""
        readable_error = get_readable_error(error)
        logger.error(f"Error {context}: {readable_error}")
        return {
            'success': False,
            'error': readable_error
        }

    def get_router_address(self) -> str:
        """Get the router address for this DEX"""
        pass

    def get_and_increment_nonce(self):
        """Get current nonce and increment in a thread-safe manner"""
        with self.nonce_lock:
            # First check current chain state
            current_nonce = self.w3.eth.get_transaction_count(self.address, 'pending')
            # If our stored nonce is behind, catch up
            if self._next_nonce < current_nonce:
                self._next_nonce = current_nonce
            # Get and increment
            nonce = self._next_nonce
            self._next_nonce += 1
        return nonce

    async def approve_token(self, token_address: str, amount: int, spender: str) -> Dict[str, Any]:
        """Approve token spending"""
        try:
            logger.info(f"Approving {amount} of token {token_address} for spender {spender}")
            token = self.w3.eth.contract(address=token_address, abi=self.token_abi)
            
            # Check current allowance
            allowance = await asyncio.to_thread(
                lambda: token.functions.allowance(self.address, spender).call()
            )
            logger.info(f"Current allowance: {allowance}")

            if allowance >= amount:
                logger.info("Sufficient allowance already exists")
                return {'success': True}

            # Build approve transaction
            approve_function = token.functions.approve(spender, amount)
            tx = approve_function.build_transaction({
                'from': self.address,
                'nonce': self.get_and_increment_nonce(),
                'type': 2,  # EIP-1559
                'maxFeePerGas': Web3.to_wei('4', 'gwei'),
                'maxPriorityFeePerGas': Web3.to_wei('2', 'gwei')
            })
            logger.info("Built transaction parameters")

            # Sign transaction
            signed_tx = await asyncio.to_thread(
                lambda: self.w3.eth.account.sign_transaction(tx, private_key=self.account.key)
            )
            logger.info("Transaction signed")

            # Send transaction
            tx_hash = await asyncio.to_thread(
                lambda: self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            )
            logger.info(f"Transaction sent: {tx_hash.hex()}")

            # Wait for transaction receipt
            receipt = await asyncio.to_thread(
                lambda: self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
            )
            logger.info(f"Transaction receipt: {receipt}")

            if receipt['status'] == 1:
                return {
                    'success': True,
                    'transactionHash': receipt['transactionHash'].hex(),
                    'gas_used': receipt['gasUsed'],
                    'blockNumber': receipt['blockNumber']
                }
            else:
                return {
                    'success': False,
                    'error': 'Transaction failed',
                    'receipt': receipt
                }

        except Exception as e:
            return self._handle_error(e, "approving token")

    async def get_token_balance(self, token_address: str) -> float:
        """Get token balance including pending transactions"""
        try:
            token = self.w3.eth.contract(
                address=token_address,
                abi=self.token_abi
            )
            decimals = await asyncio.to_thread(lambda: token.functions.decimals().call())
            logger.info(f"Token {token_address} decimals: {decimals}")
            raw_balance = await asyncio.to_thread(
                lambda: token.functions.balanceOf(self.address).call(
                    block_identifier='pending'
                )
            )
            logger.info(f"Raw balance for {token_address}: {raw_balance}")
            balance = raw_balance / (10 ** decimals)
            logger.info(f"Calculated balance: {balance}")
            return balance
        except Exception as e:
            logger.error(f"Error fetching balance: {str(e)}")
            return self._handle_error(e, "fetching token balance")
