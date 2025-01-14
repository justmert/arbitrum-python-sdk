Eth Deposit To Different Address
================================
Check out this tutorial on GitHub: `eth_deposit_to_different_address <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/eth_deposit_to_different_address>`__


``eth_deposit_to_different_address`` shows how to move Ether (or your
chain’s native token if you’re using a custom gas token) from the parent
chain into an Arbitrum or Orbit chain, to an address different than the
depositor.

How it works (under the hood)
-----------------------------

For the common case of depositing Ether (or your chain’s native token)
to the same account on the child chain, use the tutorial
`eth_deposit  <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/eth_deposit/README.md>`__.

In this specific case, we will use a retryable ticket (Arbitrum’s
canonical method for creating cross-chain messages) to deposit the
chain’s native token (e.g. Ether) into a different address. We will use
the parameter ``l2CallValue`` of the retryable ticket to specify the
amount of assets to deposit, and ``callValueRefundAddress`` to specify
the destination address. For more info on retryable tickets, see `this
page of the Arbitrum
documentation <https://docs.arbitrum.io/how-arbitrum-works/l1-to-l2-messaging#eth-deposits>`__.

Using the Arbitrum SDK
----------------------

Our `Arbitrum SDK <https://github.com/justmert/arbitrum-python-sdk>`__
provides a simply convenience method for depositing Ether (or your
chain’s native token), abstracting away the need for the client to
connect to any contracts manually.

See `exec.py  <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/eth_deposit_to_different_address/scripts/exec.py>`__ for inline explanation.

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

Install

.. code:: sh

   pip install -r requirements.txt

Run the script:

.. code:: sh

   python3 scripts/exec.py

.. raw:: html

   <p align="left">

.. raw:: html

   </p>
