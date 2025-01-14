Tutorials
=========

This section contains various tutorials and examples to help you get started with building on Arbitrum chains using Python. The tutorials demonstrate how to interact with Arbitrum chains (including Orbit chains) — deploying and using contracts directly on Arbitrum, moving Ether and tokens between the parent and child chains, and more.

The tutorials provided here are based on the official `Arbitrum TypeScript SDK <https://github.com/OffchainLabs/arbitrum-sdk>`_ and have been rewritten in Python using the `Arbitrum Python SDK <https://github.com/justmert/arbitrum-python-sdk>`_.

Basic Tutorials
-------------

Learn the basics of building on Arbitrum with these simple DApp examples:

.. toctree::
   :maxdepth: 1

   tutorials/demo_dapp_pet_shop
   tutorials/demo_dapp_election

Asset Bridging
-------------

Learn how to move assets between chains:

.. toctree::
   :maxdepth: 1

   tutorials/eth_deposit
   tutorials/eth_deposit_to_different_address
   tutorials/eth_withdraw
   tutorials/token_deposit
   tutorials/token_withdraw
   tutorials/contract_deposit

General Interoperability
----------------------

Understand cross-chain communication and verification:

.. toctree::
   :maxdepth: 1

   tutorials/greeter
   tutorials/outbox_execute
   tutorials/parent_chain_confirmation_checker
   tutorials/block_verification_in_parent_chain_assertion

Advanced Features
---------------

Explore advanced Arbitrum features and customizations:

.. toctree::
   :maxdepth: 1

   tutorials/address_table
   tutorials/custom_token_bridging
   tutorials/custom_gateway_bridging
   tutorials/delayed_inbox_l2_msg
   tutorials/redeem_pending_retryable
   tutorials/gas_estimation
   tutorials/l1_l3_teleport

Custom Network Configuration
--------------------------

These tutorials can be used with any Arbitrum chain (including Orbit chains). To use them with a custom chain:

1. Create a ``customNetwork.json`` file with your chain information
2. The chain information can be obtained using the ``prepareArbitrumNetwork`` method from the Orbit SDK
3. For tutorials involving multiple chains (like l1-l3-teleport), include an array of chain information objects

Disclaimer
---------

The code contained within these tutorials is meant for testing purposes only and does not guarantee any level of security. It has not undergone any formal audit or security analysis. Use it at your own risk. Any potential damages or security breaches occurring from the use of this code are not the responsibility of the author(s) or contributor(s). Please exercise caution and due diligence while using this code in any environment.
