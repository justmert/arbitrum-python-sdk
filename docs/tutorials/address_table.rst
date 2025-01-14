Address Table
=============
Check out this tutorial on GitHub: `address_table <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/address_table>`__


The Address table is a precompiled contract on Arbitrum chains for
registering addresses which are then retrievable by an integer index;
this saves gas by minimizing precious calldata required to input an
address as a parameter.

This demo shows a simple contract with affordances to retrieve an
address from a contract by its index in the address table, and a
client-side script to pre-register the given address (if necessary).

See `exec.py  <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/address_table/scripts/exec.py>`__ for inline comments / explanation.

Run
~~~

Install dependencies and build the contracts:

.. code:: sh

   chmod +x ./build.sh && ./build.sh

Run the script:

.. code:: sh

   python3 scripts/exec.py

Set environment variables
-------------------------

Set the values shown in ``.env-sample`` as environmental variables. To
copy it into a ``.env`` file:

.. code:: bash

   cp .env-sample .env

You’ll still need to edit some variables, i.e., ``PRIVATE_KEY`` and
``CHAIN_RPC``.

Note that you can also set the environment variables in an ``.env`` file
in the root of the monorepo, which will be available in all tutorials.

More info
~~~~~~~~~

See our `developer documentation for more
info <https://docs.arbitrum.io/>`__.

.. raw:: html

   <p align="left">

.. raw:: html

   </p>
