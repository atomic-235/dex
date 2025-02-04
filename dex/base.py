"""
Base DEX implementation.
"""

import time
import logging
from web3 import Web3
from eth_account.datastructures import SignedTransaction
from typing import Dict, Any, Optional, Union, Tuple
from .error_constants import get_readable_error
from .config import GAS_LIMIT


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

        self._pending_txs = {}
        self._nonce = None  # Initialize nonce tracking
        
    def _handle_error(self, error: Union[Exception, Tuple[str, str]], context: str) -> Dict[str, Any]:
        """Handle errors in a consistent way across all DEX implementations"""
        readable_error = get_readable_error(error)
        logger.error(f"Error {context}: {readable_error}")
        return {
            'success': False,
            'error': readable_error
        }
        
    def _build_tx(self, function) -> Dict:
        """Build a transaction with standard gas settings"""
        # Get the latest block to estimate gas prices
        block = self.w3.eth.get_block('latest')
        base_fee = block['baseFeePerGas']
        
        # Set gas prices - use 2x base fee for maxFeePerGas
        max_fee = base_fee * 2
        
        # Set priority fee - ensure it's at least 50 wei (network minimum)
        # Also set it to 10% of base fee if that's higher
        priority_fee = max(50, base_fee // 10)
        
        # Log gas settings for debugging
        logger.info(f"Gas settings - base fee: {base_fee} wei, max fee: {max_fee} wei, priority fee: {priority_fee} wei")
        
        return function.build_transaction({
            'from': self.address,
            'type': 2,  # EIP-1559
            'maxFeePerGas': max_fee,
            'maxPriorityFeePerGas': priority_fee,
            'gas': GAS_LIMIT
        })

    def _wait_for_pending_txs(self, token_in: str, token_out: str):
        """Wait for any pending transactions involving these tokens"""
        # Get current nonce
        current_pending = self._pending_txs
        latest_nonce = self.w3.eth.get_transaction_count(self.address, 'latest')
        logger.info(f"[_wait_for_pending_txs] Current pending transactions: {current_pending}")
        logger.info(f"[_wait_for_pending_txs] Latest nonce: {latest_nonce}")

        token_pair = tuple(sorted([token_in.lower(), token_out.lower()]))
        if token_pair in self._pending_txs:
            tx_hash = self._pending_txs[token_pair]
            logger.info(f"[_wait_for_pending_txs] Waiting for pending transaction {tx_hash} for pair {token_pair}")
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            logger.info(f"[_wait_for_pending_txs] Transaction {tx_hash} mined in block {receipt['blockNumber']}")
            del self._pending_txs[token_pair]

    def get_router_address(self) -> str:
        """Get the router address for this DEX"""
        pass

    def get_nonce(self):
        """Get the next available nonce for this account
        
        This method manages nonce tracking to ensure sequential operations.
        """
        # Always get a fresh nonce from pending state
        pending_nonce = self.w3.eth.get_transaction_count(self.address, 'pending')
        latest_nonce = self.w3.eth.get_transaction_count(self.address, 'latest')
        
        # Use the highest nonce we can find
        next_nonce = max(pending_nonce, latest_nonce)
        logger.info(f"Got nonces - pending: {pending_nonce}, latest: {latest_nonce}, using: {next_nonce}")
        
        return next_nonce

    def approve_token(self, token_address: str, amount: int, spender: str) -> Dict[str, Any]:
        """Approve token spending"""
        try:
            logger.info(f"Approving {amount} of token {token_address} for spender {spender}")
            token = self.w3.eth.contract(address=token_address, abi=self.token_abi)
            
            # Check current allowance
            allowance = token.functions.allowance(self.address, spender).call()
            logger.info(f"Current allowance: {allowance}")

            if allowance >= amount:
                logger.info("Sufficient allowance already exists")
                return {'success': True}

            # Build approve transaction
            approve_function = token.functions.approve(spender, amount)
            tx = self._build_tx(approve_function)
            
            # Get latest nonce right before signing
            tx['nonce'] = self.get_nonce()
            logger.info("Built transaction parameters")

            # Sign transaction
            signed_tx = self.w3.eth.account.sign_transaction(tx, private_key=self.account.key)
            logger.info("Transaction signed")

            # Send transaction
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            logger.info(f"Transaction sent: {tx_hash.hex()}")

            # Wait for transaction receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
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

    def get_token_balance(self, token_address: str) -> float:
        """Get token balance"""
        try:
            token = self.w3.eth.contract(
                address=token_address,
                abi=self.token_abi
            )
            # Get latest block number for consistent state
            block = self.w3.eth.block_number
            decimals = token.functions.decimals().call()
            logger.info(f"Token {token_address} decimals: {decimals}")
            logger.info(f"Checking balance for address: {self.address} at block {block}")
            raw_balance = token.functions.balanceOf(self.address).call(
                block_identifier=block
            )
            logger.info(f"Raw balance for {token_address}: {raw_balance}")
            balance = raw_balance / (10 ** decimals)
            logger.info(f"Calculated balance: {balance}")
            return balance
        except Exception as e:
            logger.error(f"Error fetching balance: {str(e)}")
            return self._handle_error(e, "fetching token balance")
