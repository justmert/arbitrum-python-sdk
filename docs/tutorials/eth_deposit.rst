Eth Deposit
===========
Check out this tutorial on GitHub: `eth_deposit <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/eth_deposit>`__


``eth_deposit`` shows how to move Ether (or your chain’s native token if
you’re using a custom gas token) from the parent chain into an Arbitrum
or Orbit chain.

How it works (under the hood)
-----------------------------

A user deposits the chain’s native token (e.g. Ether) onto an Arbitrum
chain using Arbitrum’s general Parent-to-child message passing system,
and simply passing the desired Ether as callvalue and no additional
data. For more info, see `this page of the Arbitrum
documentation <https://docs.arbitrum.io/how-arbitrum-works/l1-to-l2-messaging#eth-deposits>`__.

Using the Arbitrum SDK
----------------------

Our `Arbitrum SDK <https://github.com/justmert/arbitrum-python-sdk>`__
provides a simply convenience method for depositing Ether (or your
chain’s native token), abstracting away the need for the client to
connect to any contracts manually.

See `./exec.py  <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/eth_deposit/scripts/exec.py>`__ for inline explanation.

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

.. code:: sh

   pip install -r requirements.txt

Run the script:

.. code:: sh

   python3 scripts/exec.py

.. raw:: html

   <p align="left">

.. raw:: html

   </p>
