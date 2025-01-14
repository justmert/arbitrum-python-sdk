Block Verification In Parent Chain Assertion
============================================
Check out this tutorial on GitHub: `block_verification_in_parent_chain_assertion <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/block_verification_in_parent_chain_assertion>`__


This tutorial shows how to verify whether a block of a chain has been
processed as part of an RBlock assertion on its parent chain.

It uses the ``Rollup`` contract to find the latest confirmed (or created
if configured in the script) RBlock/node, find the event that created
it, and get the latest processed block hash of the child chain that’s
part of the assertion of that RBlock/node.

Then it checks whether the block number passed as argument was created
before the latest block hash of the child chain processed.

See `exec.py  <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/block_verification_in_parent_chain_assertion/scripts/exec.py>`__ for inline explanations.

Set environment variables
-------------------------

Set the values shown in ``.env-sample`` as environmental variables. To
copy it into a ``.env`` file:

.. code:: bash

   cp .env-sample .env

You’ll still need to edit some variables, i.e., ``CHAIN_RPC`` and
``PARENT_CHAIN_RPC``.

Note that you can also set the environment variables in an ``.env`` file
in the root of the monorepo, which will be available in all tutorials.

Run
---

Install dependencies:

.. code:: sh

   pip install -r requirements.txt

Run the script:

.. code:: shell

   python3 scripts/exec.py {block_number}

.. raw:: html

   <p align="left">

.. raw:: html

   </p>
