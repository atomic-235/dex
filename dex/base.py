"""
Base DEX implementation.
"""

import asyncio
import logging
from web3 import Web3
from eth_account.datastructures import SignedTransaction
from typing import Dict, Any, Optional

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

    def get_router_address(self) -> str:
        """Get the router address for this DEX"""
        pass

    async def get_nonce(self) -> int:
        """Get current nonce for the account"""
        try:
            nonce = await asyncio.to_thread(
                lambda: self.w3.eth.get_transaction_count(self.address)
            )
            logger.info(f"Current nonce: {nonce}")
            return nonce
        except Exception as e:
            logger.error(f"Error getting nonce: {str(e)}")
            raise

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
                'nonce': await self.get_nonce()
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
            logger.error(f"Error approving token: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
