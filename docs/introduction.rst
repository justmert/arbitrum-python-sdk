Introduction
============

The Arbitrum Python SDK is a powerful TypeScript library that
streamlines interactions with Arbitrum networks. It offers robust tools
for bridging tokens and passing messages between networks through an
intuitive interface to the underlying smart contracts.

**Key Features**

-  Token Bridging: Effortlessly bridge tokens between Ethereum and
   Arbitrum.
-  Message Passing: Seamlessly pass messages across networks.
-  Contracts Interface: Leverage a strongly-typed interface for
   interacting with smart contracts.

Below is an overview of the Arbitrum Python SDK functionality. See the
`tutorials <tutorials.html>`_ for more examples.

Install
-------

.. code:: sh

   pip3 install arbitrum_py

Using the Arbitrum Python SDK
-----------------------------

Bridging assets
~~~~~~~~~~~~~~~

Arbitrum Python SDK can be used to bridge assets to or from an Arbitrum
Network. The following asset bridgers are currently available:

-  :doc:`EthBridger <api/asset_bridger/eth_bridger>`
-  :doc:`Erc20Bridger <api/asset_bridger/erc20_bridger>`

All asset bridgers have the following methods which accept different
parameters depending on the asset bridger type:

-  :ref:`deposit <deposit>` - moves assets from the Parent to the Child chain
-  :ref:`withdraw <withdraw>` - moves assets from the Child to the Parent chain

Example ETH Deposit to Arbitrum One
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code:: py

   from web3 import Web3
   from src.lib.data_entities.networks import get_arbitrum_network
   from src.lib.asset_bridger.eth_bridger import EthBridger

   # get the ArbitrumNetwork object using the chain id of the Arbitrum One chain
   child_network = get_arbitrum_network(42161)
   eth_bridger = EthBridger(child_network)

   eth_deposit_receipt = eth_bridger.deposit({
       'amount': Web3.to_wei(23, 'ether'),
       'parentSigner': parent_signer,    # a SignerOrProvider instance connected to mainnet ethereum
       'childProvider': child_provider,  # a Web3 provider connected to Arbitrum One
   })

   print(f"Deposit initiated: {eth_deposit_receipt['transactionHash'].hex()}")

`Learn more in the Eth Deposit tutorial <tutorials/eth_deposit.html>`_

Example ETH Withdrawal from Arbitrum One
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code:: py

   from web3 import Web3
   from src.lib.data_entities.networks import get_arbitrum_network
   from src.lib.asset_bridger.eth_bridger import EthBridger

   # get the ArbitrumNetwork object using the chain id of the Arbitrum One chain
   child_network = get_arbitrum_network(42161)
   eth_bridger = EthBridger(child_network)

   withdraw_receipt = eth_bridger.withdraw({
       'amount': Web3.to_wei(23, 'ether'),
       'childSigner': child_signer,     # a SignerOrProvider instance connected to Arbitrum One
       'destinationAddress': child_signer.account.address,
   })

   print(f"Withdrawal initiated: {withdraw_receipt['transactionHash'].hex()}")

`Learn more in the Eth Withdraw tutorial <tutorials/eth_withdraw.html>`_

Networks
~~~~~~~~

Arbitrum Python SDK comes pre-configured for Mainnet and Sepolia, and
their Arbitrum counterparts. Any other networks that are not
pre-configured **must** be registered before being used.

Configuring Network
^^^^^^^^^^^^^^^^^^^

To interact with a custom :doc:`ArbitrumNetwork <api/data_entities/networks>`, you can
register it using the :ref:`register_custom_arbitrum_network <register_custom_arbitrum_network>` function.

.. code:: py

   from src.lib.data_entities.networks import register_custom_arbitrum_network

   register_custom_arbitrum_network({
       'chainId': 123456, 
       'name': 'Custom Arbitrum Network',
   })

Cross chain messages
~~~~~~~~~~~~~~~~~~~~

When assets are moved by the Parent and Child cross chain messages are
sent. The lifecycles of these messages are encapsulated in the classes
:doc:`ParentToChildMessage <api/message/parent_to_child_message>` and
:doc:`ChildToParentMessage <api/message/child_to_parent_message>`.
These objects are commonly created from the receipts of transactions
that send cross chain messages. A cross chain message will eventually
result in a transaction being executed on the destination chain, and
these message classes provide the ability to wait for that finalizing
transaction to occur.

Redeem a Parent-to-Child Message
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code:: py

   from src.lib.message.parent_transaction import ParentTransactionReceipt
   from src.lib.message.parent_to_child_message import ParentToChildMessageStatus

   # Create parent transaction receipt from a transaction receipt that triggered 
   # a Parent-to-Child message (e.g., depositing a token via a bridge)
   parent_txn_receipt = ParentTransactionReceipt(txn_receipt)

   # Get parent to child messages
   messages = parent_txn_receipt.get_parent_to_child_messages(
       child_signer  # SignerOrProvider instance
   )
   parent_to_child_message = messages[0]

   # Wait for status
   result = parent_to_child_message.wait_for_status()
   status = result['status']

   if status == ParentToChildMessageStatus.FUNDS_DEPOSITED_ON_CHILD:
       # Message wasn't auto-redeemed; redeem it now:
       response = parent_to_child_message.redeem()
       receipt = response.wait_for_redeem()
   elif status == ParentToChildMessageStatus.REDEEMED:
       # Message successfully redeemed
       pass

`Learn more in the Redeem Failed Retryable Tickets tutorial <tutorials/redeem_pending_retryable.html>`_

Inbox Tools
~~~~~~~~~~~

As part of normal operation, the Arbitrum sequencer will send messages
into the rollup chain. However, if the sequencer is unavailable and not
posting batches, the inbox tools can be used to force the inclusion of
transactions into the Arbitrum network.

Here's how you can use the inbox tools to withdraw ether from Arbitrum
One without waiting for the sequencer:

.. code:: py

   from src.lib.data_entities.networks import get_arbitrum_network
   from src.lib.inbox.inbox import InboxTools
   from src.lib.data_entities.constants import ARB_SYS_ADDRESS
   from src.lib.utils.helper import load_contract

   # type(parent_signer) == SignerOrProvider
   # type(child_provider) == Web3

   # Get network and create InboxTools instance
   child_network = get_arbitrum_network(child_provider.eth.chain_id)
   inbox_sdk = InboxTools(parent_signer, child_network)

   # Create ArbSys contract instance and encode withdraw function call
   arb_sys = load_contract(
       provider=child_provider,
       contract_name="ArbSys",
       address=ARB_SYS_ADDRESS
   )

   child_calldata = arb_sys.encodeABI(
       fn_name='withdrawEth',
       args=[parent_signer.account.address]
   )

   # Prepare transaction request
   tx_child_request = {
       'data': child_calldata,
       'to': ARB_SYS_ADDRESS,
       'value': 1,
   }

   # Sign and send transaction
   child_signed_tx = inbox_sdk.sign_child_tx(
       tx_child_request, 
       child_signer
   )
   child_tx_hash = parse_raw_tx(child_signed_tx)['hash']
   results_parent = inbox_sdk.send_child_signed_tx(child_signed_tx)

   inbox_receipt = parent_provider.eth.wait_for_transaction_receipt(
       results_parent.transactionHash
   )

`Learn more in the Delayed Inbox tutorial <tutorials/delayed_inbox_l2_msg.html>`_

Utils
~~~~~

-  :doc:`EventFetcher <api/utils/event_fetcher>` - A utility to
   provide typing for the fetching of events
-  :doc:`MultiCaller <api/utils/multicall>` - A utility for
   executing multiple calls as part of a single RPC request. This can be
   useful for reducing round trips.
-  :doc:`constants <api/data_entities/constants>` - A list of
   useful Arbitrum related constants

Development
-----------

Run Integration tests
~~~~~~~~~~~~~~~~~~~~~

1. Set up test nodes by following the instructions
   `here <https://docs.arbitrum.io/run-arbitrum-node/run-local-full-chain-simulation>`__
   or below quick setup:

.. code:: sh

   # Make sure docker is installed
   git clone -b release --recurse-submodules https://github.com/OffchainLabs/nitro-testnode.git && cd nitro-testnode
   chmod +x ./test-node.bash && && ./test-node.bash --init --tokenbridge --l3node --l3-token-bridge --blockscout --detach

   # (Optional) You can fund default accounts with ETH using the following command
   # https://docs.arbitrum.io/run-arbitrum-node/run-local-full-chain-simulation#blockscout

   # Send 5 ETH to the dev account in L2 network. 
   ./test-node.bash script send-l2 --to 0x3f1Eae7D46d88F08fc2F8ed27FCb2AB183EB2d0E --ethamount 5

   # Send 5 ETH to the dev account in 12 network. 
   ./test-node.bash script send-l1 --to 0x3f1Eae7D46d88F08fc2F8ed27FCb2AB183EB2d0E --ethamount 5

1. Copy ``.env.example`` to ``.env`` and update relevant environment
   variables.

2. Install dependencies:

.. code:: sh

   pip install -r requirements.txt

4. Generate the network configuration against your active Nitro test
   node:

.. code:: sh

   python3 -m scripts.gen_network

5. Execute the integration tests:

.. code:: sh

   pytest tests
