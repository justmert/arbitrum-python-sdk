Token Withdraw
==============
Check out this tutorial on GitHub: `token_withdraw <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/token_withdraw>`__


``token_withdraw`` shows how to move ERC-20 tokens from a chain to its
parent chain (e.g. from Arbitrum to Ethereum).

Note that this repo covers initiating a token withdrawal; for a demo on
releasing the funds from the Outbox, see
`outbox_execute  <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/outbox_execute/README.md>`__.

How it works (under the hood)
-----------------------------

To withdraw a token from an Arbitrum chain, a message is send from a
gateway contract which burns the token on the origin chain, and sends a
message to its parent chain, which allow the token to be released from
escrow once the dispute period is expired.

For more info, see `child-to-parent
messages <https://docs.arbitrum.io/how-arbitrum-works/l2-to-l1-messaging>`__.

Standard ERC-20 withdrawal
--------------------------

In this tutorial, we deploy a fresh token and then deposit some to the
child chain. Then, we use these new tokens to trigger a withdrawal back
to the parent chain.

We use our `Arbitrum
SDK <https://github.com/justmert/arbitrum-python-sdk>`__ library for the
token bridge interactions.

See `exec.py  <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/token_withdraw/scripts/exec.py>`__ for inline explanation.

Set environment variables
-------------------------

Set the values shown in ``.env-sample`` as environmental variables. To
copy it into a ``.env`` file:

.. code:: bash

   cp .env-sample .env

You’ll still need to edit some variables, i.e., ``PRIVATE_KEY``,
``CHAIN_RPC`` and ``PARENT_CHAIN_RPC``.

Note that you can also set the environment variables in an ``.env`` file
in the root of the monorepo, which will be available in all tutorials.

Run
---

Install dependencies and build the contracts:

::

   chmod +x build.sh && ./build.sh

Run the script:

::

   python3 scripts/exec.py

.. raw:: html

   <p align="left">

.. raw:: html

   </p>
