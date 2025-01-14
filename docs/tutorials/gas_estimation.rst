Gas Estimation
==============
Check out this tutorial on GitHub: `gas_estimation <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/gas_estimation>`__


``gas_estimation`` is a simple demo of how a developer can estimate
transaction fees on Arbitrum.

It uses the formula described in this Medium article to estimate the
fees to be paid on a transaction, also estimating each component of the
formula sepparately: `Understanding Arbitrum: 2-Dimensional
Fees <https://medium.com/offchainlabs/understanding-arbitrum-2-dimensional-fees-fd1d582596c9>`__.
For more information, you can also see `How to estimate
gas <https://docs.arbitrum.io/build-decentralized-apps/how-to-estimate-gas>`__
in the Arbitrum documentation portal.

See `exec.py  <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/gas_estimation/scripts/exec.py>`__ for inline explanations.

Set environment variables
-------------------------

Set the values shown in ``.env-sample`` as environmental variables. To
copy it into a ``.env`` file:

.. code:: bash

   cp .env-sample .env

You’ll still need to edit some variables, i.e., ``CHAIN_RPC``.

Note that you can also set the environment variables in an ``.env`` file
in the root of the monorepo, which will be available in all tutorials.

Run
---

Inside the script, you can edit the ``tx_data`` constant to suit your
needs.

Run the script:

::

   python3 scripts/exec.py

.. raw:: html

   <p align="left">

.. raw:: html

   </p>
