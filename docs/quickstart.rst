Quickstart
==========

This guide will help you get started with the Arbitrum Python SDK.

Basic Usage
----------

Here's a simple example of how to use the SDK:

.. code-block:: python

    from arbitrum_sdk import AssetBridger
    from web3 import Web3

    # Initialize Web3
    w3 = Web3(Web3.HTTPProvider('YOUR_RPC_URL'))

    # Create an AssetBridger instance
    bridger = AssetBridger(w3)

    # Now you can use the bridger to interact with Arbitrum
    # For example, to check the parent network:
    parent_network = bridger.check_parent_network()
