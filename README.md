# Arbitrum Python SDK

[![npm version](https://badge.fury.io/js/%40arbitrum%2Fsdk.svg)](https://badge.fury.io/js/@arbitrum%2Fsdk.svg)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

A TypeScript library for client-side interactions with Arbitrum. The Arbitrum Python SDK provides essential helper functionality and direct access to underlying smart contract interfaces, enabling developers to build powerful applications on the Arbitrum network.

> [!IMPORTANT]
>
> This is the code and documentation here are based on the official [@arbitrum/sdk v4](https://github.com/OffchainLabs/arbitrum-sdk) and have been rewritten in Python. Based release version: [v4.0.2](https://github.com/OffchainLabs/arbitrum-sdk/tree/v4.0.2)
>
> This repository is a community effort and is not officially supported by Offchain Labs. Please see the [disclaimer](#disclaimer) at the end of this document.

* 📚 [Documentation](https://arbitrum-python-sdk.readthedocs.io)
* 💡 [Tutorials](https://github.com/justmert/arbitrum-python-tutorials)

## Table of Contents

- [Arbitrum Python SDK](#arbitrum-python-sdk)
  - [Table of Contents](#table-of-contents)
  - [Overview](#overview)
  - [Installation](#installation)
  - [Key Features](#key-features)
    - [Bridging Assets](#bridging-assets)
    - [Cross-Chain Messages](#cross-chain-messages)
    - [Network Configuration](#network-configuration)
  - [Usage](#usage)
  - [Running Integration Tests](#running-integration-tests)
  - [Documentation](#documentation)
  - [License](#license)
  - [Disclaimer](#disclaimer)

## Overview

Arbitrum Python SDK simplifies the process of interacting with Arbitrum chains, offering a robust set of tools for asset bridging and cross-chain messaging.

## Installation

```bash
pip3 install arbitrum_py
```

## Key Features

### Bridging Assets

Arbitrum Python SDK facilitates the bridging of assets between an Arbitrum chain and its parent chain. Currently supported asset bridgers:

- `EthBridger`: For bridging ETH to and from an Arbitrum chain (L2 or L3)
- `Erc20Bridger`: For bridging ERC-20 tokens to and from an Arbitrum chain (L2 or L3)
- `EthL1L3Bridger`: For bridging ETH to an L3 directly from L1
- `Erc20L1L3Bridger`: For bridging ERC-20 tokens to an L3 directly from L1

### Cross-Chain Messages

Cross-chain communication is handled through `ParentToChildMessage` and `ChildToParentMessage` classes. These encapsulate the lifecycle of messages sent between chains, typically created from transaction receipts that initiate cross-chain messages.

### Network Configuration

The SDK comes preconfigured for Arbitrum One, Arbitrum Nova and Arbitrum Sepolia. Custom Arbitrum networks can be registered using `register_custom_arbitrum_network`, which is required before utilizing other SDK features.

## Usage

Here's a basic example of using the SDK to bridge ETH:

```python
from web3 import Web3
from eth_account import Account
from arbitrum_py.data_entities.networks import get_arbitrum_network
from arbitrum_py.asset_bridger.eth_bridger import EthBridger
from arbitrum_py.data_entities.signer_or_provider import SignerOrProvider

def bridge_eth(parent_signer: SignerOrProvider, child_chain_id: int):
    child_network = get_arbitrum_network(child_chain_id)
    eth_bridger = EthBridger(child_network)

    deposit = eth_bridger.deposit({
        'amount': Web3.to_wei(0.1, 'ether'),
        'parentSigner': parent_signer,
    })

    print(f"Deposit initiated: {deposit['transactionHash'].hex()}")
```

For more detailed usage examples and API references, please refer to the [Arbitrum Python SDK documentation](https://arbitrum-python-sdk.readthedocs.io) or check out the [tutorials](https://github.com/justmert/arbitrum-python-tutorials)

## Running Tests

1. Set up test nodes by following the instructions [here](https://docs.arbitrum.io/run-arbitrum-node/run-local-full-chain-simulation) or below quick setup:

  ```sh
  # Make sure docker is installed
  git clone -b release --recurse-submodules https://github.com/OffchainLabs/nitro-testnode.git && cd nitro-testnode
  chmod +x ./test-node.bash && && ./test-node.bash --init --tokenbridge --l3node --l3-token-bridge --blockscout --detach

  # (Optional) You can fund default accounts with ETH using the following command
  # https://docs.arbitrum.io/run-arbitrum-node/run-local-full-chain-simulation#blockscout

  # Send 5 ETH to the dev account in L2 network. 
  ./test-node.bash script send-l2 --to 0x3f1Eae7D46d88F08fc2F8ed27FCb2AB183EB2d0E --ethamount 5

  # Send 5 ETH to the dev account in 12 network. 
  ./test-node.bash script send-l1 --to 0x3f1Eae7D46d88F08fc2F8ed27FCb2AB183EB2d0E --ethamount 5
  ```

1. Copy `.env.example` to `.env` and update relevant environment variables.

2. Install dependencies:

  ```sh
  pip install -r requirements.txt
  ```

4. Generate the network configuration against your active Nitro test node:

  ```sh
  python3 -m scripts.gen_network
  ```

5. Execute the integration tests:

  ```sh
  pytest tests
  ```

## Documentation

For comprehensive guides and API documentation, visit the [Arbitrum Python SDK Documentation](https://arbitrum-python-sdk.readthedocs.io). You can also find tutorials in the [Arbitrum Python Tutorials](https://github.com/justmert/arbitrum-python-tutorials)

## License

Arbitrum Python SDK is released under the [Apache 2.0 License](LICENSE).

## Disclaimer

The code contained within this package is meant for testing purposes only and does not guarantee any level of security. It has not undergone any formal audit or security analysis. Use it at your own risk. Any potential damages or security breaches occurring from the use of this code are not the responsibility of the author(s) or contributor(s) of this repository. Please exercise caution and due diligence while using this code in any environment.
