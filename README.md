# Arbitrum Python SDK

Python library for client-side interactions with Arbitrum. Arbitrum Python SDK provides common helper functionality as well as access to the underlying smart contract interfaces.

Below is an overview of the Arbitrum Python SDK functionality.

> **Note**: Arbitrum Python SDK is NOT official and currently in alpha. It is NOT recommended for production use. Go to [Arbitrum Typescript SDK](https://github.com/OffchainLabs/arbitrum-sdk) for official library.

### Quickstart Recipes

- ##### Deposit Ether Into Arbitrum

```py
from src.lib.data_entities.networks import get_l2_network
from src.lib.asset_briger.eth_bridger import EthBridger
from src.lib.data_entities.signer_or_provider import SignerOrProvider
from web3 import Web3, HTTPProvider, Account

l2_network = get_l2_network(
    l2_chain_id  # <-- chain id of target Arbitrum chain
)
eth_bridger = EthBridger(l2_network)


l1_provider = Web3(HTTPProvider(l1_url))
l2_provider = Web3(HTTPProvider(l2_url))
account = Account.from_key(private_key)

l1_signer = SignerOrProvider(
    account,  # <-- instance of web3.Account
    l1_provider,
)

eth_deposit_tx_response = await eth_bridger.deposit({"amount": 23, "l1Signer": l1_signer, "l2Provider": l2_provider})
```

- ##### Redeem an L1 to L2 Message

```py
from src.lib.data_entities.signer_or_provider import SignerOrProvider
from src.lib.message.l1_transaction import L1TransactionReceipt
from src.lib.message.l1_to_l2_message import L1ToL2MessageStatus
from web3 import Web3, HTTPProvider, Account


l1_txn_receipt = L1TransactionReceipt(
    txn_receipt,  # <-- web3.py transaction receipt dict of an Ethereum tx that triggered an L1 to L2 message (say depositting a token via a bridge)
)

l2_provider = Web3(HTTPProvider(l2_url))
l2_signer = SignerOrProvider(
    account,  # <-- instance of web3.Account
    l2_provider,
)

l1_to_l2_message = await l1_txn_receipt.get_l1_to_l2_messages(
    l2_signer  # <-- instance of SignerOrProvider
)[0]


res = await l1_to_l2_message.wait_for_status()

if res.status == L1ToL2MessageStatus.FUNDS_DEPOSITED_ON_L2:
    # Message wasn't auto-redeemed; redeem it now:
    response = await l1_to_l2_message.redeem()
    receipt = await response.wait()
```

- ##### Check if sequencer has included a transaction in L1 data

```py
from web3 import Web3, HTTPProvider
from src.lib.message.l2_transaction import L2TransactionReceipt
import time

l1_provider = Web3(HTTPProvider(l1_url))
l2_provider = Web3(HTTPProvider(l2_url))

l2_txn_receipt = L2TransactionReceipt(
    txn_receipt # <-- web3.py transaction receipt dict of an Arbitrum tx
)

# wait 3 minutes:
time.sleep(60 * 3)

# if dataIsOnL1, sequencer has posted it and it inherits full rollup/L1 security
data_is_on_l1 = await l2_txn_receipt.is_data_available(l2_provider, l1_provider)
```

### Bridging assets

Arbitrum Python SDK can be used to bridge assets to/from the rollup chain. The following asset bridgers are currently available:

- EthBridger
- Erc20Bridger

All asset bridgers have the following methods:

- **deposit** - moves assets from the L1 to the L2
- **deposit_estimate_gas** - estimates the gas required to do the deposit
- **withdraw** - moves assets from the L2 to the L1
- **withdraw_estimate_gas** - estimates the gas required to do the withdrawal
  Which accept different parameters depending on the asset bridger type

### Cross chain messages

When assets are moved by the L1 and L2 cross chain messages are sent. The lifecycles of these messages are encapsulated in the classes `L1ToL2Message` and `L2ToL1Message`. These objects are commonly created from the receipts of transactions that send cross chain messages. A cross chain message will eventually result in a transaction being executed on the destination chain, and these message classes provide the ability to wait for that finalizing transaction to occur.

### Networks

Arbitrum Python SDK comes pre-configured for Mainnet and Goerli, and their Arbitrum counterparts. However, the networks functionality can be used to register networks for custom Arbitrum instances. Most of the classes in Arbitrum Python SDK depend on network objects so this must be configured before using other Arbitrum Python SDK functionality.

### Inbox tools

As part of normal operation the Arbitrum sequencer will send messages into the rollup chain. However, if the sequencer is unavailable and not posting batches, the inbox tools can be used to force the inclusion of transactions into the rollup chain.

### Utils

- **EventFetcher** - A utility to provide typing for the fetching of events
- **MultiCaller** - A utility for executing multiple calls as part of a single RPC request. This can be useful for reducing round trips.
- **constants** - A list of useful Arbitrum related constants

### Run tests

1. First, make sure you have a Nitro test node running. Follow the instructions [here](https://docs.arbitrum.io/node-running/how-tos/local-dev-node).

2. Install the library dependencies by running `pip install -r requirements.txt`.

3. After the node has started up (that could take up to 20-30 mins), run `python3 -m src.scripts.gen_network`.

4. Once done, finally run `pytest tests/` to run the integration tests.

### Note

The Arbitrum Python SDK was converted from the Arbitrum TypeScript SDK. To avoid being prone to errors and to facilitate ease of use, some functionalities have retained the structure from the TypeScript code, which may have made the library less Pythonic. For example, the use of async in scenarios where there is no need for asynchronous behavior.
