"""
Uniswap V3 DEX implementation.
"""

import asyncio
import logging
from web3 import Web3
from typing import List, Dict, Any, Optional

from .base import BaseDEX
from .config import (
    UNISWAP_ROUTER_ADDRESS,
    UNISWAP_FACTORY_ADDRESS,
    UNISWAP_QUOTER_ADDRESS,
    UNISWAP_ROUTER_ABI,
    UNISWAP_FACTORY_ABI,
    UNISWAP_QUOTER_ABI,
    ERC20_ABI,
    GAS_LIMIT,
    USDC_ADDRESS,
    cbBTC_ADDRESS,
    UNISWAP_FEE_TIER
)

logger = logging.getLogger(__name__)


class UniswapV3DEX(BaseDEX):
    """Uniswap V3 DEX implementation"""

    def __init__(self, w3: Web3, private_key: str):
        """Initialize Uniswap V3 DEX"""
        super().__init__(w3, private_key)
        self.token_abi = ERC20_ABI
        self.router = self.w3.eth.contract(
            address=UNISWAP_ROUTER_ADDRESS,
            abi=UNISWAP_ROUTER_ABI
        )
        self.quoter = self.w3.eth.contract(
            address=UNISWAP_QUOTER_ADDRESS,
            abi=UNISWAP_QUOTER_ABI
        )
        self.slippage = 0.01  # 1% slippage tolerance
        self._pending_txs = {}

    @property
    def router_address(self) -> str:
        """Get the router address for this DEX"""
        return self.router.address

    def encode_path(self, token_addresses: List[str], fees: List[int]) -> bytes:
        """Encode path for Uniswap V3"""
        path = b''
        for i in range(len(token_addresses) - 1):
            path += Web3.to_bytes(hexstr=token_addresses[i][2:]).rjust(20, b'\0')
            path += Web3.to_bytes(fees[i]).rjust(3, b'\0')
        path += Web3.to_bytes(hexstr=token_addresses[-1][2:]).rjust(20, b'\0')
        return path

    async def get_quote(self, token_in: str, token_out: str, amount_in: int) -> int:
        """Get quote for token swap"""
        try:
            # Ensure addresses are checksummed
            token_in = Web3.to_checksum_address(token_in)
            token_out = Web3.to_checksum_address(token_out)

            # Encode path with fee tier
            path = self.encode_path([token_in, token_out], [UNISWAP_FEE_TIER])

            # Get quote
            quote = await asyncio.to_thread(
                self.quoter.functions.quoteExactInput(
                    path,
                    int(amount_in)  # Ensure amount is int
                ).call
            )

            return int(quote[0])  # Return amountOut and ensure it's int

        except Exception as e:
            return self._handle_error(e, "getting quote")


    async def swap_tokens(self, token_in: str, token_out: str, amount_in: int, current_balance: Optional[int] = None) -> Dict[str, Any]:
        """
        Swap tokens using Uniswap V3 router
        """
        try:
            # Wait for any pending transactions first
            await self._wait_for_pending_txs(token_in, token_out)
            # Wait for any pending transactions involving these tokens
            token_pair = tuple(sorted([token_in.lower(), token_out.lower()]))
            if token_pair in self._pending_txs:
                tx_hash = self._pending_txs[token_pair]
                logger.info(f"Waiting for pending transaction {tx_hash.hex()} to complete")
                await asyncio.to_thread(
                    lambda: self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                )
                del self._pending_txs[token_pair]
            
            logger.info(f"Starting swap of {amount_in} {token_in} to {token_out}")

            # Convert addresses to checksum format
            token_in_addr = Web3.to_checksum_address(token_in)
            token_out_addr = Web3.to_checksum_address(token_out)
            token = self.w3.eth.contract(address=token_in_addr, abi=self.token_abi)

            # Check balance after any pending transactions complete
            if current_balance is None:
                balance = await asyncio.to_thread(lambda: token.functions.balanceOf(self.address).call({'block_identifier': 'latest'}))
            else:
                balance = current_balance
            if balance < amount_in:
                return {'success': False, 'error': f'Insufficient balance: have {balance}, need {amount_in}'}
            
            # Get quote for validation
            quote = await self.get_quote(token_in_addr, token_out_addr, amount_in)
            if isinstance(quote, dict) and not quote.get('success'):
                return quote  # Return error from quote
            logger.info(f"Got quote: {quote}")

            # Calculate minimum amount out with slippage
            min_amount_out = int(quote * (1 - self.slippage))
            logger.info(f"Min amount out with {self.slippage*100}% slippage: {min_amount_out}")

            # Prepare swap parameters
            params = {
                'tokenIn': token_in_addr,
                'tokenOut': token_out_addr,
                'fee': UNISWAP_FEE_TIER,
                'recipient': self.address,
                'amountIn': int(amount_in),  # Ensure amount is int
                'amountOutMinimum': min_amount_out,
                'sqrtPriceLimitX96': 0
            }

            # Build transaction
            swap_function = self.router.functions.exactInputSingle(params)
            nonce = await self.get_nonce()
            tx = await asyncio.to_thread(
                lambda: swap_function.build_transaction({
                    'from': self.address,
                    'nonce': nonce,
                    'type': 2,  # EIP-1559
                    'maxFeePerGas': Web3.to_wei('4', 'gwei'),
                    'maxPriorityFeePerGas': Web3.to_wei('2', 'gwei'),
                    'value': 0  # No ETH being sent
                })
            )
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
                lambda: self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            )
            logger.info(f"Transaction receipt: {receipt}")

            if receipt['status'] == 1:
                # Store this as a completed transaction
                token_pair = tuple(sorted([token_in.lower(), token_out.lower()]))
                self._pending_txs[token_pair] = tx_hash
                return {
                    'success': True,
                    'transactionHash': receipt['transactionHash'].hex(),
                    'amount_out': min_amount_out,
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
            return self._handle_error(e, "executing swap")
