"""ERC20 token utilities"""

import os
import json
import logging
from pathlib import Path
from decimal import Decimal
from web3 import Web3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Load ERC20 ABI
with open(Path(__file__).parent / 'abis' / 'erc20_abi.json', 'r') as f:
    ERC20_ABI = json.load(f)

class ERC20Token:
    """Utility class for ERC20 token operations"""
    
    def __init__(self, w3: Web3, token_address: str, decimals: int = None):
        """Initialize ERC20 token
        
        Args:
            w3: Web3 instance
            token_address: Token contract address
            decimals: Token decimals (optional, will be fetched from contract if not provided)
        """
        self.w3 = w3
        self.token_address = token_address
        self.contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
        self.decimals = decimals or self.contract.functions.decimals().call()
        
    async def get_balance(self, address: str) -> Decimal:
        """Get token balance for address
        
        Args:
            address: Address to check balance for
            
        Returns:
            Balance in token's smallest unit (e.g. wei for ETH, satoshi for BTC)
        """
        try:
            balance = self.contract.functions.balanceOf(address).call()
            return Decimal(balance)
        except Exception as e:
            logger.error(f"Error getting balance for {self.token_address}: {str(e)}")
            raise
