L1 L3 Teleport
==============
Check out this tutorial on GitHub: `l1_l3_teleport <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/l1_l3_teleport>`__


This tutorial shows how to bridge tokens from L1 to an Arbitrum L3.

It uses the `Teleport
Contracts <https://github.com/OffchainLabs/l1-l3-teleport-contracts>`__
to send ERC-20 tokens through an L2's canonical token bridge, and then
again through an L3's canonical token bridge. The entire process only
requires a single user transaction on L1 (excluding token approval).

To bridge ETH, it uses a "double retryable", i.e. a retryable that
creates another retryable. You can read more about retryable tickets
`here <https://docs.arbitrum.io/how-arbitrum-works/l1-to-l2-messaging>`__.

See `initiate_deposit.py <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/l1_l3_teleport/scripts/initiate_deposit.py>`__ for
initiating an ERC-20 deposit.

See `initiate_eth_deposit.py <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/l1_l3_teleport/scripts/initiate_eth_deposit.py>`__
for initiating an ETH deposit.

See
`monitor_deposit_status.py <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/l1_l3_teleport/scripts/monitor_deposit_status.py>`__
for monitoring ERC-20 deposits.

See
`monitor_eth_deposit_status.py <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/l1_l3_teleport/scripts/monitor_eth_deposit_status.py>`__
for monitoring ETH deposits.

Paying for retryables
---------------------

When initiating an ERC-20 deposit, there are multiple ways retryable
fees can be paid.

There are 2 (or 3) L1-to-L2 retryables and 1 L2-to-L3 retryable created
during a deposit. By default, the L1-to-L2 retryables will be paid for
in ETH when the deposit is initiated.

If the L3 uses ETH for fees, by default, the L2-to-L3 retryable will be
paid for in ETH when the deposit is initiated.

If the L3 uses a custom gas token that is available on L1, by default,
the L2-to-L3 retryable will be paid for in the fee token when the
deposit is initiated. This requires an extra approval transaction.

If [the L3 uses a custom gas token] AND [that token is unavailable on L1
OR ``skip_fee_token`` is passed to ``get_deposit_request``], the
L2-to-L3 retryable will NOT be paid for when the deposit is initiated.
If the L2-to-L3 retryable is not paid for up front, it must be
eventually manually redeemed on L3. Manually redeeming retryables is
permissionless. See instructions
`here <https://docs.arbitrum.io/how-arbitrum-works/l1-to-l2-messaging#manual-redemption>`__
to manually redeem a retryable ticket.

Set environment variables
-------------------------

Set the values shown in ``.env-sample`` as environmental variables. To
copy it into a ``.env`` file:

.. code:: shell

   cp .env-sample .env

You’ll still need to edit some variables, i.e., ``PRIVATE_KEY``,
``CHAIN_RPC``, ``PARENT_CHAIN_RPC`` and ``L1_RPC``.

Note that you can also set the environment variables in an ``.env`` file
in the root of the monorepo, which will be available in all tutorials.

Run
~~~

Install dependencies:

.. code:: shell

   pip3 install -r requirements.txt

Run the scripts:

.. code:: shell

   python3 scripts/initiate_deposit.py --help

.. code:: shell

   python3 scripts/initiate_eth_deposit.py --help

.. code:: shell

   python3 scripts/monitor_deposit_status.py <txHash>

.. code:: shell

   python3 scripts/monitor_eth_deposit_status.py <txHash>

.. raw:: html

   <p align="left">

.. raw:: html

   </p>
