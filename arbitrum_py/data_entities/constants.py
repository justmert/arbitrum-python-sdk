from typing import Final

# System contract addresses
NODE_INTERFACE_ADDRESS: Final[str] = "0x00000000000000000000000000000000000000C8"
"""Address of the Node Interface contract."""

ARB_SYS_ADDRESS: Final[str] = "0x0000000000000000000000000000000000000064"
"""Address of the ArbSys contract."""

ARB_RETRYABLE_TX_ADDRESS: Final[str] = "0x000000000000000000000000000000000000006E"
"""Address of the ArbRetryableTx contract."""

ARB_ADDRESS_TABLE_ADDRESS: Final[str] = "0x0000000000000000000000000000000000000066"
"""Address of the ArbAddressTable contract."""

ARB_OWNER_PUBLIC: Final[str] = "0x000000000000000000000000000000000000006B"
"""Address of the ArbOwnerPublic contract."""

ARB_GAS_INFO: Final[str] = "0x000000000000000000000000000000000000006C"
"""Address of the ArbGasInfo contract."""

ARB_STATISTICS: Final[str] = "0x000000000000000000000000000000000000006F"
"""Address of the ArbStatistics contract."""

ADDRESS_ZERO: Final[str] = "0x0000000000000000000000000000000000000000"
"""The zero address."""

# Block time and timing constants
ARB_MINIMUM_BLOCK_TIME_IN_SECONDS: Final[float] = 0.25
"""The minimum time between blocks in seconds."""

SEVEN_DAYS_IN_SECONDS: Final[int] = 7 * 24 * 60 * 60
"""Seven days in seconds (7 * 24 * 60 * 60)."""

# The offset added to an L1 address to get the corresponding L2 address.
# This is used to prevent address collisions between L1 and L2.
ADDRESS_ALIAS_OFFSET: Final[str] = "0x1111000000000000000000000000000000001111"
"""
The offset added to an L1 address to get the corresponding L2 address.
This is used to prevent address collisions between L1 and L2.
"""

# Address of the gateway a token will be assigned to if it is disabled.
# This is used in the token bridging system to mark tokens as unbridgeable.
DISABLED_GATEWAY: Final[str] = "0x0000000000000000000000000000000000000001"
"""
Address of the gateway a token will be assigned to if it is disabled.
This is used in the token bridging system to mark tokens as unbridgeable.
"""

# If a custom token is enabled for Arbitrum it will implement a function
# called isArbitrumEnabled which returns this value (42161 = 0xa4b1).
# This value matches Arbitrum One's chain ID.
CUSTOM_TOKEN_IS_ENABLED: Final[int] = 42161
"""
If a custom token is enabled for Arbitrum it will implement a function
called isArbitrumEnabled which returns this value (42161 = 0xa4b1).
This value matches Arbitrum One's chain ID.
"""

# How long to wait (in milliseconds) for a deposit to arrive before timing out.
# Finalization on mainnet can take up to 2 epochs = 64 blocks.
# We add 10 minutes for system processing plus buffer time.
# Total timeout: 30 minutes
DEFAULT_DEPOSIT_TIMEOUT: Final[int] = 30 * 60 * 1000
"""
How long to wait (in milliseconds) for a deposit to arrive before timing out.
Finalization on mainnet can take up to 2 epochs = 64 blocks.
We add 10 minutes for system processing plus buffer time.
Total timeout: 30 minutes
"""

# Nitro upgrade block numbers for Arbitrum One
# The L1 block at which Nitro was activated
# See: https://etherscan.io/block/15447158
ARB1_NITRO_GENESIS_L1_BLOCK: Final[int] = 15447158
"""
The L1 block at which Nitro was activated.
See: https://etherscan.io/block/15447158
"""

# The L2 block at which Nitro was activated
# See: https://arbiscan.io/block/22207817
ARB1_NITRO_GENESIS_L2_BLOCK: Final[int] = 22207817
"""
The L2 block at which Nitro was activated.
See: https://arbiscan.io/block/22207817
"""

# Maximum uint256 value (2^256 - 1)
# Used as the default approval amount for token transfers
MAX_UINT256: Final[int] = (1 << 256) - 1
"""
Maximum uint256 value (2^256 - 1).
Used as the default approval amount for token transfers.
"""
