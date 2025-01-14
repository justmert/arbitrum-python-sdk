Delayed Inbox L2 Msg
====================
Check out this tutorial on GitHub: `delayed_inbox_l2_msg <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/delayed_inbox_l2_msg>`__


``delayed_inbox_l2_msg`` shows how to send a signed transaction to your
chain (also referred to as an L2Message) only using an RPC of the parent
chain. This demo has 2 parts:

1. how to send a normal signed transaction using the delayed inbox
   (`./scripts/normal_tx.py  <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/delayed_inbox_l2_msg/scripts/normal_tx.py>`__)
2. how to withdraw your funds back without sending a transaction
   directly to the sequencer
   (`./scripts/withdraw_funds.py  <https://github.com/justmert/arbitrum-python-tutorials/tree/master/tutorials/delayed_inbox_l2_msg/scripts/withdraw_funds.py>`__)

Bypassing the sequencer
-----------------------

This tutorial also shows the initial step to take if the `sequencer is
misbehaving <https://docs.arbitrum.io/how-arbitrum-works/sequencer#unhappyuncommon-case-sequencer-isnt-doing-its-job>`__.
In that case, after 24 hours have passed from the moment the message was
sent from the parent chain, you can use the SequencerInbox’s
``forceInclusion`` method to move it from the delayed inbox into the
core inbox, at which point it’s considered finalized.

You can also use the `Arbitrum
SDK <https://github.com/justmert/arbitrum-python-sdk/blob/master/src/lib/inbox/inbox.py>`__
to force include your transaction.

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

.. code:: bash

   chmod +x ./build.sh && ./build.sh

Normal transaction:

.. code:: bash

   python3 scripts/normal_tx.py

Withdraw funds:

.. code:: bash

   python3 scripts/withdraw_funds.py

.. raw:: html

   <p align="left">

.. raw:: html

   </p>
