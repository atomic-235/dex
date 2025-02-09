"""
A generalized DEX manager for working with different DEXes.
"""

import logging
import asyncio
from decimal import Decimal
from typing import Dict, Any, Optional, Union, List
from web3 import Web3
from enum import Enum, auto

from .uniswap import UniswapV3DEX
from .aerodrome import AerodromeDEX
from .base import BaseDEX
from .config import (
    USDC_ADDRESS, USDbC_ADDRESS, WETH_ADDRESS, AERO_ADDRESS,
    cbBTC_ADDRESS, WBTC_ADDRESS, ETH_ADDRESS
)

logger = logging.getLogger(__name__)


class Token(Enum):
    """Supported tokens with their addresses"""
    USDC = auto()
    USDbC = auto()
    WETH = auto()
    AERO = auto()
    cbBTC = auto()
    WBTC = auto()
    ETH = auto()


# Mapping of token symbols to addresses
TOKEN_ADDRESSES = {
    Token.USDC: USDC_ADDRESS,
    Token.USDbC: USDbC_ADDRESS,
    Token.WETH: WETH_ADDRESS,
    Token.AERO: AERO_ADDRESS,
    Token.cbBTC: cbBTC_ADDRESS,
    Token.WBTC: WBTC_ADDRESS,
    Token.ETH: ETH_ADDRESS  # Zero address represents native ETH
}


class DEXManager:
    """A generalized DEX manager for easy interaction with different DEXes"""

    def __init__(self, w3: Web3, private_key: str):
        """Initialize DEX manager with Web3 instance and private key"""
        self.w3 = w3
        self.private_key = private_key
        self.dexes: Dict[str, BaseDEX] = {
            'uniswap': UniswapV3DEX(w3, private_key),
            'aerodrome': AerodromeDEX(w3, private_key)
        }

    def _get_token_address(self, token: Union[str, Token]) -> str:
        """Convert token symbol or enum to address"""
        if isinstance(token, str):
            # Try exact match first
            try:
                token = Token[token]
            except KeyError:
                # Try case-insensitive match
                token_map = {
                    'CBBTC': Token.cbBTC,
                    'USDC': Token.USDC,
                    'USDBC': Token.USDbC,
                    'WETH': Token.WETH,
                    'AERO': Token.AERO,
                    'WBTC': Token.WBTC
                }
                try:
                    token = token_map[token.upper()]
                except KeyError:
                    raise ValueError(f"Unsupported token symbol: {token}")
        
        if token not in TOKEN_ADDRESSES:
            raise ValueError(f"Unsupported token: {token}")
        
        return TOKEN_ADDRESSES[token]

    def get_token_balance(self, token: Union[str, Token]) -> int:
        """Get token balance for the account
        
        Args:
            token: Token symbol (e.g. 'USDC') or Token enum
        
        Returns:
            Token balance in smallest units (e.g. wei)
        """
        token_address = self._get_token_address(token)
        
        # Handle ETH balance specially since it's not an ERC20 token
        if token_address == ETH_ADDRESS:
            account = self.w3.eth.account.from_key(self.private_key)
            return self.w3.eth.get_balance(account.address)
        
        # For ERC20 tokens, use DEX instance to get the balance
        dex = next(iter(self.dexes.values()))
        logger.info(f"Using DEX with address: {dex.address}")
        raw_balance = dex.get_token_balance(token_address)
        
        # Convert from decimal back to wei/satoshis
        token_contract = self.w3.eth.contract(
            address=token_address,
            abi=dex.token_abi
        )
        decimals = token_contract.functions.decimals().call()
        return int(raw_balance * (10 ** decimals))

    def get_exchange_rate(
        self,
        token_in: Union[str, Token],
        token_out: Union[str, Token],
        amount_in: Union[int, Decimal],
        dex_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get the exchange rate between two tokens.
        
        Args:
            token_in: Address of input token
            token_out: Address of output token
            amount_in: Amount of input token (in wei or Decimal)
            dex_name: Optional name of DEX to use. If not provided, will check all DEXes.
        
        Returns:
            Dict containing:
            - success: bool indicating if operation was successful
            - rate: Exchange rate as Decimal
            - amount_out: Expected output amount
            - dex: Name of DEX providing this rate
            - error: Error message if success is False
        """
        try:
            # Get token addresses
            token_in_address = self._get_token_address(token_in)
            token_out_address = self._get_token_address(token_out)

            # Convert Decimal to wei if needed
            if isinstance(amount_in, Decimal):
                token = self.w3.eth.contract(
                    address=token_in_address,
                    abi=self.dexes['uniswap'].token_abi  # All DEXes use same ABI
                )
                decimals = token.functions.decimals().call()
                amount_in_wei = int(amount_in * Decimal(10**decimals))
            else:
                amount_in_wei = amount_in

            best_rate = None
            best_amount = 0
            best_dex = None

            # If specific DEX requested, only check that one
            dexes_to_check = [dex_name] if dex_name else self.dexes.keys()

            # First check which DEXes have valid pools
            valid_dexes = []
            for dex_name in dexes_to_check:
                dex = self.dexes[dex_name]
                if hasattr(dex, 'get_pool_exists'):
                    # For DEXes that support pool checking
                    try:
                        if dex.get_pool_exists(token_in_address, token_out_address, True) or \
                           dex.get_pool_exists(token_in_address, token_out_address, False):
                            valid_dexes.append(dex_name)
                    except Exception as e:
                        logger.warning(f"Failed to check pool on {dex_name}: {str(e)}")
                        continue
                else:
                    # For DEXes that don't support pool checking, try getting a quote
                    try:
                        quote = dex.get_quote(token_in_address, token_out_address, amount_in_wei)
                        if quote > 0:
                            valid_dexes.append(dex_name)
                    except Exception as e:
                        logger.warning(f"Failed to get quote from {dex_name}: {str(e)}")
                        continue

            # Then get quotes only from valid DEXes
            for dex_name in valid_dexes:
                dex = self.dexes[dex_name]
                try:
                    quote = dex.get_quote(token_in_address, token_out_address, amount_in_wei)
                    if quote > best_amount:
                        best_amount = quote
                        best_dex = dex_name
                        
                        # Calculate rate based on decimals for both tokens
                        token_in_contract = self.w3.eth.contract(
                            address=token_in_address,
                            abi=dex.token_abi
                        )
                        token_out_contract = self.w3.eth.contract(
                            address=token_out_address,
                            abi=dex.token_abi
                        )
                        decimals_in = token_in_contract.functions.decimals().call()
                        decimals_out = token_out_contract.functions.decimals().call()
                        
                        # Rate = output_amount / input_amount
                        best_rate = (Decimal(str(quote)) / Decimal(10**decimals_out)) / \
                                  (Decimal(str(amount_in_wei)) / Decimal(10**decimals_in))
                except Exception as e:
                    logger.warning(f"Failed to get quote from {dex_name}: {str(e)}")
                    continue

            if best_rate is None:
                return {
                    'success': False,
                    'error': 'No valid quotes found from any DEX'
                }

            return {
                'success': True,
                'rate': best_rate,
                'amount_out': best_amount,
                'dex': best_dex
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def swap_tokens(
        self,
        token_in: Union[str, Token],
        token_out: Union[str, Token],
        amount_in: Union[int, Decimal],
        dex_name: Optional[str] = None,
        max_slippage: Optional[Decimal] = None
    ) -> Dict[str, Any]:
        """
        Swap tokens using the specified or best available DEX.
        
        Args:
            token_in: Address of input token
            token_out: Address of output token
            amount_in: Amount of input token (in wei or Decimal)
            dex_name: Optional name of DEX to use. If not provided, will use best rate.
            max_slippage: Maximum allowed slippage as decimal (e.g., 0.01 for 1%)
        
        Returns:
            Dict containing transaction result with fields like:
            - success: bool indicating if swap was successful
            - transactionHash: Hash of the transaction if successful
            - error: Error message if swap failed
            - dex: Name of DEX used for swap
        """
        try:
            # Get token addresses
            token_in_address = self._get_token_address(token_in)
            token_out_address = self._get_token_address(token_out)

            # First get best rate if DEX not specified
            if not dex_name:
                rate_result = self.get_exchange_rate(token_in, token_out, amount_in)
                if not rate_result['success']:
                    return rate_result
                dex_name = rate_result['dex']

            dex = self.dexes[dex_name]

            # Convert Decimal to wei if needed
            if isinstance(amount_in, Decimal):
                token = self.w3.eth.contract(
                    address=token_in_address,
                    abi=dex.token_abi
                )
                decimals = token.functions.decimals().call()
                amount_in_wei = int(amount_in * Decimal(10**decimals))
            else:
                amount_in_wei = amount_in

            # Set slippage if provided
            if max_slippage is not None:
                dex.slippage = float(max_slippage)

            # Approve token if needed
            dex.approve_token(token_in_address, amount_in_wei, dex.router_address)

            # Execute swap
            result = dex.swap_tokens(token_in_address, token_out_address, amount_in_wei)
            if result.get('success', False):
                result['dex'] = dex_name


            return result

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
