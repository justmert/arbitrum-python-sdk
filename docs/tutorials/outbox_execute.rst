Outbox Execute
==============
Check out this tutorial on GitHub: `outbox_execute <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/outbox_execute>`__


The outbox contract is responsible for receiving and executing all
“outgoing” messages; i.e., messages passed from a chain to its parent
chain (for example, from Arbitrum to Ethereum).

The (expected) most-common use-case is withdrawals (of, i.e., Ether or
tokens), but the outbox handles any arbitrary contract call, as this
tutorial illustrates.

See `exec.py  <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/outbox_execute/scripts/exec.py>`__ for inline comments / explanation.

`Click
here <https://docs.arbitrum.io/how-arbitrum-works/l2-to-l1-messaging>`__
for more information on child-to-parent message passing.

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

   python3 exec.py 0xmytxnhash

-  *0xmytxnhash* is expected to be the transaction hash of a transaction
   in the child chain that triggered a child-to-parent message.

.. raw:: html

   <p align="left">

.. raw:: html

   </p>
