"""
Ethereum (Sepolia testnet) configuration for live alpha integration.

In production these would point to Ethereum mainnet contracts.
For alpha testing, we deploy mock XAUT/PAXG + SOSTEscrow on Sepolia.
"""

# Sepolia testnet RPC — public endpoint (rate-limited)
SEPOLIA_RPC = "https://rpc.sepolia.org"

# Deployed mock token addresses on Sepolia (replace after deployment)
MOCK_XAUT_ADDRESS = "0x0000000000000000000000000000000000000000"  # TODO: deploy MockERC20 as XAUT
MOCK_PAXG_ADDRESS = "0x0000000000000000000000000000000000000000"  # TODO: deploy MockERC20 as PAXG

# Deployed SOSTEscrow contract on Sepolia (replace after deployment)
ESCROW_ADDRESS = "0x0000000000000000000000000000000000000000"  # TODO: deploy SOSTEscrow

# Watcher parameters
ETH_CONFIRMATIONS = 6
ETH_POLL_INTERVAL = 15  # seconds

# Mainnet token addresses (for reference, NOT used in alpha)
MAINNET_XAUT = "0x68749665FF8D2d112Fa859AA293F07A622782F38"
MAINNET_PAXG = "0x45804880De22913dAFE09f4980848ECE6EcbAf78"
