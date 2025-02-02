"""
Aerodrome DEX implementation.
"""

import asyncio
import logging
from web3 import Web3
from typing import List, Dict, Any, Tuple, Optional
from eth_typing import ChecksumAddress

from .base import BaseDEX
from .config import (
    AERODROME_ROUTER_ADDRESS,
    AERODROME_FACTORY_ADDRESS,
    AERODROME_ROUTER_ABI,
    AERODROME_FACTORY_ABI,
    ERC20_ABI,
    cbBTC_ADDRESS
)

logger = logging.getLogger(__name__)


class Route:
    """Represents a route for Aerodrome swaps"""
    def __init__(self, from_token: str, to_token: str, stable: bool, factory: str):
        self.from_token = Web3.to_checksum_address(from_token)
        self.to_token = Web3.to_checksum_address(to_token)
        self.stable = stable
        self.factory = Web3.to_checksum_address(factory)

    def to_tuple(self) -> Tuple[ChecksumAddress, ChecksumAddress, bool, ChecksumAddress]:
        """Convert to tuple format expected by the contract"""
        return (self.from_token, self.to_token, self.stable, self.factory)


class AerodromeDEX(BaseDEX):
    """Aerodrome DEX implementation"""

    @property
    def router_address(self) -> str:
        """Get the router address for this DEX"""
        return self._router_address

    def __init__(self, w3: Web3, private_key: str):
        """Initialize Aerodrome DEX"""
        super().__init__(w3, private_key)
        self.token_abi = ERC20_ABI
        self._router_address = AERODROME_ROUTER_ADDRESS
        self.factory_address = AERODROME_FACTORY_ADDRESS
        self.router = self.w3.eth.contract(
            address=self._router_address,
            abi=AERODROME_ROUTER_ABI
        )
        self.factory = self.w3.eth.contract(
            address=self.factory_address,
            abi=AERODROME_FACTORY_ABI
        )
        self.slippage = 0.01  # 1% slippage tolerance

    async def get_pool_exists(self, token_a: str, token_b: str, stable: bool) -> bool:
        """Check if pool exists"""
        try:
            pool = await asyncio.to_thread(
                self.factory.functions.getPool(
                    Web3.to_checksum_address(token_a),
                    Web3.to_checksum_address(token_b),
                    stable
                ).call
            )
            logger.info(f"Pool address for {token_a} -> {token_b} (stable={stable}): {pool}")
            return pool != '0x0000000000000000000000000000000000000000'
        except Exception as e:
            error_result = self._handle_error(e, "checking pool existence")
            return False

    async def get_quote(self, token_in: str, token_out: str, amount_in: int) -> int:
        """Get quote for a swap"""
        try:
            # First try direct path
            direct_quote = await self._try_path([token_in, token_out], amount_in)
            if direct_quote > 0:
                logger.info(f"Direct quote found: {direct_quote}")
                return direct_quote

            raise Exception("No valid quotes found")

        except Exception as e:
            return self._handle_error(e, "getting quote")

    async def _try_path(self, path: List[str], amount_in: int) -> int:
        """Try to get a quote for a specific path"""
        try:
            routes = []
            for i in range(len(path) - 1):
                token_in = path[i]
                token_out = path[i + 1]

                # Try both stable and volatile pools
                stable_pool_exists = await self.get_pool_exists(token_in, token_out, True)
                volatile_pool_exists = await self.get_pool_exists(token_in, token_out, False)

                logger.info(f"Pool check {token_in} -> {token_out}: stable={stable_pool_exists}, volatile={volatile_pool_exists}")

                if stable_pool_exists:
                    routes.append(Route(token_in, token_out, True, self.factory_address))
                elif volatile_pool_exists:
                    routes.append(Route(token_in, token_out, False, self.factory_address))
                else:
                    return 0  # No valid pool for this pair

            if not routes:
                return 0

            # Convert routes to tuples
            routes = [r.to_tuple() for r in routes]

            try:
                quote = await asyncio.to_thread(
                    self.router.functions.getAmountsOut(
                        amount_in,
                        routes
                    ).call
                )
                logger.info(f"Quote for path {path}: {quote}")
                return quote[-1]  # Return the final output amount
            except Exception as e:
                logger.error(f"Error getting quote for path {path}: {str(e)}")
                return 0

        except Exception as e:
            error_result = self._handle_error(e, f"trying path {path}")
            return 0

    async def swap_tokens(self, token_in: str, token_out: str, amount_in: int) -> Optional[Dict[str, Any]]:
        """Swap tokens using Aerodrome router"""
        try:
            logger.info(f"Starting swap of {amount_in} {token_in} to {token_out}")
            
            # Get quote first
            amount_out = await self.get_quote(token_in, token_out, amount_in)
            if amount_out == 0:
                raise Exception("Could not get valid quote")
            logger.info(f"Got quote: {amount_out}")

            # Calculate minimum amount out with slippage
            min_amount_out = int(amount_out * (1 - self.slippage))
            logger.info(f"Min amount out with {self.slippage*100}% slippage: {min_amount_out}")

            # Find the best route
            routes = []
            
            # Try direct path first
            direct_path = [token_in, token_out]
            logger.info(f"Trying direct path: {direct_path}")
            direct_route = await self._get_route(direct_path)
            if direct_route:
                routes = direct_route
                logger.info("Using direct route")
            else:
                raise Exception("No valid route found")

            logger.info(f"Final route: {routes}")

            # Build swap transaction
            deadline = self.w3.eth.get_block('latest')['timestamp'] + 1200  # 20 minutes
            logger.info(f"Transaction deadline: {deadline}")
            
            # Encode the swap function call using functions
            swap_function = self.router.functions.swapExactTokensForTokens(
                amount_in,
                min_amount_out,
                routes,
                self.address,
                deadline
            )

            # Build transaction parameters
            tx = swap_function.build_transaction({
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

    async def _get_route(self, path: List[str]) -> List[Tuple[ChecksumAddress, ChecksumAddress, bool, ChecksumAddress]]:
        """Get the best route for a path"""
        try:
            routes = []
            for i in range(len(path) - 1):
                token_in = path[i]
                token_out = path[i + 1]

                # Try both stable and volatile pools
                stable_pool_exists = await self.get_pool_exists(token_in, token_out, True)
                volatile_pool_exists = await self.get_pool_exists(token_in, token_out, False)

                if stable_pool_exists:
                    routes.append(Route(token_in, token_out, True, self.factory_address))
                elif volatile_pool_exists:
                    routes.append(Route(token_in, token_out, False, self.factory_address))
                else:
                    return []

            return [r.to_tuple() for r in routes]

        except Exception as e:
            error_result = self._handle_error(e, "getting route")
            return []