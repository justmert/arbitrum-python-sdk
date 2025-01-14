Eth Withdraw
============
Check out this tutorial on GitHub: `eth_withdraw <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/eth_withdraw>`__


``eth_withdraw`` shows how to move Ether (or your chain’s native token
if you’re using a custom gas token) from an Arbitrum or Orbit chain into
its parent chain.

Note that this repo covers initiating a withdrawal. For a demo on
releasing the funds from the Outbox, see
`outbox_execute  <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/outbox_execute/README.md>`__

How it works (under the hood)
-----------------------------

To withdraw Ether (or your chain’s native token) from an Arbitrum chain,
a client creates an outgoing / child to parent message using the
``ArbSys`` precompile that later lets them release the asset from its
escrow in the parent chain’s Bridge contract. For more info, see `this
page of the Arbitrum
documentation <https://docs.arbitrum.io/how-arbitrum-works/l2-to-l1-messaging>`__.

Using the Arbitrum SDK
----------------------

Our `Arbitrum SDK <https://github.com/justmert/arbitrum-python-sdk>`__
provides a simply convenience method for withdrawing Ether (or your
chain’s native token), abstracting away the need for the client to
connect to any contracts manually.

See `exec.py  <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/eth_withdraw/scripts/exec.py>`__ for inline explanation.

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

Install dependencies:

::

   pip install -r requirements.txt

Run the script:

::

   python3 scripts/exec.py

*Note: Executing scripts will require your account be funded with
.000001 Eth in the child chain.*

.. raw:: html

   <p align="left">

.. raw:: html

   </p>
