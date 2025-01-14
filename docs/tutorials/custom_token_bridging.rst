Custom Token Bridging
=====================
Check out this tutorial on GitHub: `custom_token_bridging <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/custom_token_bridging>`__


There are some tokens with requirements beyond what are offered via our
starndard ERC20 gateway. ``custom_token_bridging`` demonstrates how to
get these custom tokens set up to use our generic-custom gateway.

For more info on bridging assets on Arbitrum, see our `token bridging
docs <https://docs.arbitrum.io/build-decentralized-apps/token-bridging/token-bridge-erc20>`__.

Custom token bridging using the generic-custom gateway
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Bridging a custom token to the Arbitrum chain is done via the Arbitrum
generic-custom gateway. Our generic-custom gateway is designed to be
flexible enough to be suitable for most (but not necessarily all) custom
fungible token needs.

Here, we deploy a `demo custom
token  <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/custom_token_bridging/contracts/ParentChainToken.sol>`__ to the parent chain and a
`demo custom token  <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/custom_token_bridging/contracts/ChildChainToken.sol>`__ to the child
chain. We then use the Arbitrum custom gateway contract to register our
parent chain custom token to our child chain custom token. Once done
with token’s registration to the custom gateway, we register our token
to the Arbitrum gateway router on the parent chain.

We use our `Arbitrum
SDK <https://github.com/justmert/arbitrum-python-sdk>`__ library to
initiate and verify the bridging.

See `./exec.py  <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/custom_token_bridging/scripts/exec.py>`__ for inline explanation.

Note for custom-gas-token chains
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This script also works on custom-gas-token chains. In that case, you’ll
have to add the information of your chain in the
```customNetwork.json`` <../../customNetwork.json>`__ file, which will
be loaded automatically to the Arbitrum SDK (see `How to run the
tutorials against a custom network <../../README.md>`__ for more
information). The script then will perform the extra operation needed
for custom-gas-token chains.

Set environment variables
~~~~~~~~~~~~~~~~~~~~~~~~~

Set the values shown in ``.env-sample`` as environmental variables. To
copy it into a ``.env`` file:

.. code:: bash

   cp .env-sample .env

You’ll still need to edit some variables, i.e., ``PRIVATE_KEY``,
``CHAIN_RPC`` and ``PARENT_CHAIN_RPC``.

Note that you can also set the environment variables in an ``.env`` file
in the root of the monorepo, which will be available in all tutorials.

Run
~~~

Install dependencies and build the contracts:

.. code:: bash

   chmod +x ./build.sh && ./build.sh

Run the script:

.. code:: bash

   python3 scripts/exec.py

.. raw:: html

   <p align="left">

.. raw:: html

   </p>
