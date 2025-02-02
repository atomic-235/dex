"""
Common DEX error codes and messages.
"""

from typing import Dict, Optional

# Common error signatures and their human-readable messages
ERROR_MESSAGES: Dict[str, str] = {
    "STF": "Insufficient token balance for swap",
    "Too little received": "Price moved unfavorably, try increasing slippage tolerance",
    "ds-math-sub-underflow": "Insufficient token balance",
    "INSUFFICIENT_OUTPUT_AMOUNT": "Price moved unfavorably, try increasing slippage tolerance",
    "EXCESSIVE_INPUT_AMOUNT": "Price impact too high, try smaller amount",
    "TRANSFER_FROM_FAILED": "Token transfer failed - check your balance and allowance",
    "EXPIRED": "Transaction expired, try again",
    "SafeMath: subtraction overflow": "Insufficient balance for operation",
}

def get_readable_error(error: str) -> str:
    """
    Convert blockchain error message into human-readable format.
    
    Args:
        error: Original error message or tuple from web3
        
    Returns:
        Human-readable error message
    """
    if isinstance(error, tuple):
        # Extract error message from revert tuple
        error_msg = error[0]
    else:
        error_msg = str(error)
    
    # Try to match known error messages
    for error_key, readable_msg in ERROR_MESSAGES.items():
        if error_key in error_msg:
            return readable_msg
            
    # If no match found, clean up the original message
    if "execution reverted:" in error_msg:
        error_msg = error_msg.split("execution reverted:")[1].strip()
    
    return f"Transaction failed: {error_msg}"
