Parent Chain Confirmation Checker
=================================
Check out this tutorial on GitHub: `parent_chain_confirmation_checker <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/parent_chain_confirmation_checker>`__


``parent_chain_confirmation_checker`` is a simple demo of Arbitrum’s
transaction finality checker (used to check if a transaction was already
submitted to the parent chain or not).

It calls the precompile ``NodeInterface`` to find information about a
transaction on the parent chain that includes a batch containing the
specified child chain’s transaction.

This tutorial has 2 scripts; both will show you whether your transaction
has been posted in a batch on the parent chain or not.

-  The first script, ``check_confirmation``, will output the number of
   block confirmations of the batch-posting transaction on the parent
   chain.
-  The second is ``find_submission_tx``, which will output the
   batch-posting transaction hash on the parent chain.

See `exec.py  <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/parent_chain_confirmation_checker/scripts/exec.py>`__ for inline explanations.

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

Script 1: check if the transaction is already on a batch on the parent
chain:

.. code:: sh

   python3 scripts/exec.py --action check_confirmation --tx-hash {YOUR_TX_HASH}

Script 2: get the transaction hash on the parent chain that includes a
batch that contains a given transaction of the child chain:

.. code:: sh

   python3 scripts/exec.py --action find_submission_tx --tx-hash {YOUR_TX_HASH}

.. raw:: html

   <p align="left">

.. raw:: html

   </p>
