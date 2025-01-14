Redeem Pending Retryable
========================
Check out this tutorial on GitHub: `redeem_pending_retryable <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/redeem_pending_retryable>`__


Retryable tickets are the Arbitrum protocol’s canonical method for
passing generalized messages from the parent chain to a child chain (for
example, from Ethereum to Arbitrum). A retryable ticket is a message for
a chain, encoded and delivered by its parent chain; if gas is provided,
it will be executed immediately. If no gas is provided or the execution
reverts, it will be placed in the chain’s retry buffer, where any user
can re-execute for some fixed period (roughly one week).

You can use ``exec_create_failed_retryable`` script to create a failed
retryable ticket and then use ``exec_redeem`` which shows you how to
redeem (re-execute) a ticket that is sitting in the chain’s retry
buffer.

See `exec_redeem.py  <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/redeem_pending_retryable/scripts/exec_redeem.js>`__ for inline
explanation.

`Click
here <https://docs.arbitrum.io/how-arbitrum-works/l1-to-l2-messaging>`__
for more info on retryable tickets.

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

To create a failed retryable ticket:

::

   python3 scripts/exec_create_failed_retryable.py

To redeem a pending retryable ticket:

::

   python3 scripts/exec_redeem.py --txhash 0xmytxnhash

-  *0xmytxnhash* is expected to be the transaction hash of the
   transaction on the parent chain that triggered the parent-to-child
   message.

.. raw:: html

   <p align="left">

.. raw:: html

   </p>
