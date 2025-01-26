"""
Configuration for DEX interactions
"""

from dotenv import load_dotenv
import os
import json
from web3 import Web3

load_dotenv()

# Base Network Configuration
RPC_URL = "https://mainnet.base.org"

# Contract addresses
WETH_ADDRESS = Web3.to_checksum_address("0x4200000000000000000000000000000000000006")
USDC_ADDRESS = Web3.to_checksum_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

# Token Decimals
WETH_DECIMALS = 18
USDC_DECIMALS = 6
cbBTC_DECIMALS = 8

# Uniswap contracts
UNISWAP_FACTORY_ADDRESS = Web3.to_checksum_address("0x33128a8fC17869897dcE68Ed026d694621f6FDfD")
UNISWAP_ROUTER_ADDRESS = Web3.to_checksum_address("0x2626664c2603336E57B271c5C0b26F421741e481")
UNISWAP_QUOTER_ADDRESS = Web3.to_checksum_address("0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a")  # Quoter V2

# Aerodrome contracts
AERODROME_FACTORY_ADDRESS = Web3.to_checksum_address("0x420DD381b31aEf6683db6B902084cB0FFECe40Da")
AERODROME_ROUTER_ADDRESS = Web3.to_checksum_address("0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43")

# Common tokens on Base
USDbC_ADDRESS = Web3.to_checksum_address("0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA")  # Base USD
AERO_ADDRESS = Web3.to_checksum_address("0x940181a94A35A4569E4529A3CDfB74e38FD98631")  # Aerodrome token
cbBTC_ADDRESS = Web3.to_checksum_address("0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf")  # cbBTC
WBTC_ADDRESS = Web3.to_checksum_address("0x77852193BD608A518dd7b7C2f891A1d02c2EeE10")  # WBTC

# Pool Fees (in basis points)
UNISWAP_FEE_TIER = 500  # 0.05% fee tier

# Gas settings
GAS_LIMIT = 500000
MAX_PRIORITY_FEE = 2  # gwei

# Load ABIs
def load_abi(name):
    abi_path = os.path.join(os.path.dirname(__file__), 'abis', name)
    with open(abi_path) as f:
        return json.load(f)

ERC20_ABI = load_abi('erc20_abi.json')
WETH_ABI = load_abi('weth_abi.json')

# Uniswap ABIs
UNISWAP_FACTORY_ABI = load_abi('uniswap_factory_abi.json')
UNISWAP_POOL_ABI = load_abi('uniswap_pool_abi.json')
UNISWAP_ROUTER_ABI = load_abi('uniswap_router_abi.json')
UNISWAP_QUOTER_ABI = load_abi('uniswap_quoter_abi.json')

# Aerodrome ABIs
AERODROME_FACTORY_ABI = load_abi('aerodrome_factory_abi.json')
AERODROME_POOL_ABI = load_abi('aerodrome_pool_abi.json')
AERODROME_ROUTER_ABI = load_abi('aerodrome_router_abi.json')
AERODROME_QUOTER_ABI = load_abi('aerodrome_quoter_abi.json')
