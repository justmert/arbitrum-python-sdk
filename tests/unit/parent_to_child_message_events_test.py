import pytest
from hexbytes import HexBytes
from web3 import HTTPProvider, Web3

from arbitrum_py.message.parent_to_child_message import ParentToChildMessageStatus
from arbitrum_py.message.parent_transaction import ParentTransactionReceipt


def test_does_call_for_nitro_events():
    # Receipt from mainnet tx: 0x00000a61331187be51ab9ae792d74f601a5a21fb112f5b9ac5bccb23d4d5aaba
    receipt = {
        "to": HexBytes("0x72Ce9c846789fdB6fC1f34aC4AD25Dd9ef7031ef"),
        "from": HexBytes("0xa2e06c19EE14255889f0Ec0cA37f6D0778D06754"),
        "contractAddress": None,
        "transactionIndex": 323,
        "gasUsed": 0,
        "logsBloom": HexBytes(
            "0x040001000000000000000000000000000000000000000200000000004000000000000000800004000020000000080000020000021a0000000000000000000800400000000400800000000008000008800000000000400000008000040000002000200000000000000000000000000000002001000000440000000014880000000000000000000001000000400000000000000000000000000800020000000000100000020000200000000000000000000040000000000000000000000000000000000002000000000000000000080000000000000000004000001002080000002000200400000000000000000080000000000000000000000400000200004000"
        ),
        "blockHash": HexBytes("0xe5b6457bc2ec1bb39a88cee7f294ea3ad41b76d1069fd2e69c5959b4ffd6dd56"),
        "transactionHash": HexBytes("0x00000a61331187be51ab9ae792d74f601a5a21fb112f5b9ac5bccb23d4d5aaba"),
        "logs": [
            {
                "transactionIndex": 323,
                "blockNumber": 15500657,
                "transactionHash": HexBytes(
                    HexBytes("0x00000a61331187be51ab9ae792d74f601a5a21fb112f5b9ac5bccb23d4d5aaba")
                ),
                "address": HexBytes("0x72Ce9c846789fdB6fC1f34aC4AD25Dd9ef7031ef"),
                "topics": [
                    HexBytes("0x85291dff2161a93c2f12c819d31889c96c63042116f5bc5a205aa701c2c429f5"),
                    HexBytes("0x000000000000000000000000c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"),
                    HexBytes("0x000000000000000000000000a2e06c19ee14255889f0ec0ca37f6d0778d06754"),
                    HexBytes("0x000000000000000000000000a2e06c19ee14255889f0ec0ca37f6d0778d06754"),
                ],
                "data": HexBytes("0x000000000000000000000000d92023e9d9911199a6711321d1277285e6d4e2db"),
                "logIndex": 443,
                "blockHash": HexBytes("0xe5b6457bc2ec1bb39a88cee7f294ea3ad41b76d1069fd2e69c5959b4ffd6dd56"),
                "removed": False,
            },
            {
                "transactionIndex": 323,
                "blockNumber": 15500657,
                "transactionHash": HexBytes("0x00000a61331187be51ab9ae792d74f601a5a21fb112f5b9ac5bccb23d4d5aaba"),
                "address": HexBytes("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"),
                "topics": [
                    HexBytes("0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"),
                    HexBytes("0x000000000000000000000000a2e06c19ee14255889f0ec0ca37f6d0778d06754"),
                    HexBytes("0x000000000000000000000000d92023e9d9911199a6711321d1277285e6d4e2db"),
                ],
                "data": HexBytes("0x0000000000000000000000000000000000000000000000000853a0d2313c0000"),
                "logIndex": 444,
                "blockHash": HexBytes("0xe5b6457bc2ec1bb39a88cee7f294ea3ad41b76d1069fd2e69c5959b4ffd6dd56"),
                "removed": False,
            },
            {
                "transactionIndex": 323,
                "blockNumber": 15500657,
                "transactionHash": HexBytes("0x00000a61331187be51ab9ae792d74f601a5a21fb112f5b9ac5bccb23d4d5aaba"),
                "address": HexBytes("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"),
                "topics": [
                    HexBytes("0x7fcf532c15f0a6db0bd6d0e038bea71d30d808c7d98cb3bf7268a95bf5081b65"),
                    HexBytes("0x000000000000000000000000d92023e9d9911199a6711321d1277285e6d4e2db"),
                ],
                "data": HexBytes("0x0000000000000000000000000000000000000000000000000853a0d2313c0000"),
                "logIndex": 445,
                "blockHash": HexBytes("0xe5b6457bc2ec1bb39a88cee7f294ea3ad41b76d1069fd2e69c5959b4ffd6dd56"),
                "removed": False,
            },
            {
                "transactionIndex": 323,
                "blockNumber": 15500657,
                "transactionHash": HexBytes("0x00000a61331187be51ab9ae792d74f601a5a21fb112f5b9ac5bccb23d4d5aaba"),
                "address": HexBytes("0x8315177aB297bA92A06054cE80a67Ed4DBd7ed3a"),
                "topics": [
                    HexBytes("0x5e3c1311ea442664e8b1611bfabef659120ea7a0a2cfc0667700bebc69cbffe1"),
                    HexBytes("0x000000000000000000000000000000000000000000000000000000000000504c"),
                    HexBytes("0x2a5dcbed3d730861a810a913641dd7b8d5ff3ee20b716517934795dcef1fa7a7"),
                ],
                "data": HexBytes(
                    "0x0000000000000000000000004dbd4fc535ac27206064b68ffcf827b0a60bab3f0000000000000000000000000000000000000000000000000000000000000009000000000000000000000000ea3123e9d9911199a6711321d1277285e6d4f3ec33b030be5f0dd0f325a650d7517584f9d94942bfcd0fa5f05d5ebeeb5e409af100000000000000000000000000000000000000000000000000000005e0fc4c5800000000000000000000000000000000000000000000000000000000631abc80"
                ),
                "logIndex": 446,
                "blockHash": HexBytes("0xe5b6457bc2ec1bb39a88cee7f294ea3ad41b76d1069fd2e69c5959b4ffd6dd56"),
                "removed": False,
            },
            {
                "transactionIndex": 323,
                "blockNumber": 15500657,
                "transactionHash": HexBytes("0x00000a61331187be51ab9ae792d74f601a5a21fb112f5b9ac5bccb23d4d5aaba"),
                "address": HexBytes("0x4Dbd4fc535Ac27206064B68FfCf827b0A60BAB3f"),
                "topics": [
                    HexBytes("0xff64905f73a67fb594e0f940a8075a860db489ad991e032f48c81123eb52d60b"),
                    HexBytes("0x000000000000000000000000000000000000000000000000000000000000504c"),
                ],
                "data": HexBytes(
                    "0x000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000000000000000002640000000000000000000000006c411ad3e74de3e7bd422b94a27770f5b86c623b0000000000000000000000000000000000000000000000000853a0d2313c00000000000000000000000000000000000000000000000000000854e8ab1802ca800000000000000000000000000000000000000000000000000001270f6740d880000000000000000000000000a2e06c19ee14255889f0ec0ca37f6d0778d06754000000000000000000000000a2e06c19ee14255889f0ec0ca37f6d0778d06754000000000000000000000000000000000000000000000000000000000001d5660000000000000000000000000000000000000000000000000000000011e1a30000000000000000000000000000000000000000000000000000000000000001442e567b36000000000000000000000000c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2000000000000000000000000a2e06c19ee14255889f0ec0ca37f6d0778d06754000000000000000000000000a2e06c19ee14255889f0ec0ca37f6d0778d067540000000000000000000000000000000000000000000000000853a0d2313c000000000000000000000000000000000000000000000000000000000000000000a00000000000000000000000000000000000000000000000000000000000000080000000000000000000000000000000000000000000000000000000000000004000000000000000000000000000000000000000000000000000000000000000600000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
                ),
                "logIndex": 447,
                "blockHash": HexBytes("0xe5b6457bc2ec1bb39a88cee7f294ea3ad41b76d1069fd2e69c5959b4ffd6dd56"),
                "removed": False,
            },
            {
                "transactionIndex": 323,
                "blockNumber": 15500657,
                "transactionHash": HexBytes("0x00000a61331187be51ab9ae792d74f601a5a21fb112f5b9ac5bccb23d4d5aaba"),
                "address": HexBytes("0xd92023E9d9911199a6711321D1277285e6d4e2db"),
                "topics": [
                    HexBytes("0xc1d1490cf25c3b40d600dfb27c7680340ed1ab901b7e8f3551280968a3b372b0"),
                    HexBytes("0x000000000000000000000000a2e06c19ee14255889f0ec0ca37f6d0778d06754"),
                    HexBytes("0x0000000000000000000000006c411ad3e74de3e7bd422b94a27770f5b86c623b"),
                    HexBytes("0x000000000000000000000000000000000000000000000000000000000000504c"),
                ],
                "data": HexBytes(
                    "0x000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000000000000000000000000000000000000001442e567b36000000000000000000000000c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2000000000000000000000000a2e06c19ee14255889f0ec0ca37f6d0778d06754000000000000000000000000a2e06c19ee14255889f0ec0ca37f6d0778d067540000000000000000000000000000000000000000000000000853a0d2313c000000000000000000000000000000000000000000000000000000000000000000a00000000000000000000000000000000000000000000000000000000000000080000000000000000000000000000000000000000000000000000000000000004000000000000000000000000000000000000000000000000000000000000000600000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
                ),
                "logIndex": 448,
                "blockHash": HexBytes("0xe5b6457bc2ec1bb39a88cee7f294ea3ad41b76d1069fd2e69c5959b4ffd6dd56"),
                "removed": False,
            },
            {
                "transactionIndex": 323,
                "blockNumber": 15500657,
                "transactionHash": HexBytes("0x00000a61331187be51ab9ae792d74f601a5a21fb112f5b9ac5bccb23d4d5aaba"),
                "address": HexBytes("0xd92023E9d9911199a6711321D1277285e6d4e2db"),
                "topics": [
                    HexBytes("0xb8910b9960c443aac3240b98585384e3a6f109fbf6969e264c3f183d69aba7e1"),
                    HexBytes("0x000000000000000000000000a2e06c19ee14255889f0ec0ca37f6d0778d06754"),
                    HexBytes("0x000000000000000000000000a2e06c19ee14255889f0ec0ca37f6d0778d06754"),
                    HexBytes("0x000000000000000000000000000000000000000000000000000000000000504c"),
                ],
                "data": HexBytes(
                    "0x000000000000000000000000c02aaa39b223fe8d0a0e5c4f27ead9083c756cc20000000000000000000000000000000000000000000000000853a0d2313c0000"
                ),
                "logIndex": 449,
                "blockHash": HexBytes("0xe5b6457bc2ec1bb39a88cee7f294ea3ad41b76d1069fd2e69c5959b4ffd6dd56"),
                "removed": False,
            },
        ],
        "cumulativeGasUsed": 0,
        "blockNumber": 15500657,
        "confirmations": 1033491,
        "effectiveGasPrice": 0,
        "byzantium": True,
        "type": 2,
        "status": 1,
    }

    rpc_url = "https://arb1.arbitrum.io/rpc"
    arb_provider = Web3(HTTPProvider(rpc_url))
    parent_txn_receipt = ParentTransactionReceipt(receipt)
    tx_receipt = None
    try:
        # Try getting classic messages using a nitro tx
        tx_receipt = parent_txn_receipt.get_parent_to_child_messages_classic(arb_provider)
    except Exception as err:
        # This call should throw an error
        assert isinstance(err, Exception)
        assert (
            str(err)
            == "This method is only for classic transactions. Use 'get_parent_to_child_messages' for nitro transactions."
        )
    finally:
        # Should not successfully get classic messages
        assert tx_receipt is None, "Classic method was successful using a nitro transaction."

    is_classic = parent_txn_receipt.is_classic(arb_provider)
    msg = (parent_txn_receipt.get_parent_to_child_messages(arb_provider))[0]

    assert not is_classic, "incorrect tx type returned by isClassic call"
    assert msg.chain_id == 42161, "incorrect chain id"
    assert msg.sender == "0xeA3123E9d9911199a6711321d1277285e6d4F3EC", "incorrect sender"

    assert msg.message_number == 0x504C, "incorrect message number"
    assert msg.parent_base_fee == 0x05E0FC4C58, "incorrect l1 base fee"
    assert (
        msg.message_data["destAddress"] == "0x6c411aD3E74De3E7Bd422b94A27770f5B86C623B"
    ), "incorrect dest address on message_data"
    assert msg.message_data["l2CallValue"] == 0x0853A0D2313C0000, "incorrect child chain call value on messageData"
    assert msg.message_data["l1Value"] == 0x0854E8AB1802CA80, "incorrect parent chain value on messageData"
    assert msg.message_data["maxSubmissionFee"] == 0x01270F6740D880, "incorrect max submission fee on message_data"
    assert (
        msg.message_data["excessFeeRefundAddress"] == "0xa2e06c19EE14255889f0Ec0cA37f6D0778D06754"
    ), "incorrect excess fee refund address"
    assert (
        msg.message_data["callValueRefundAddress"] == "0xa2e06c19EE14255889f0Ec0cA37f6D0778D06754"
    ), "incorrect call value refund address"
    assert msg.message_data["gasLimit"] == 0x01D566, "incorrect gas limit on message_data"
    assert msg.message_data["maxFeePerGas"] == 0x11E1A300, "incorrect max fee per gas on message_data"
    assert msg.message_data["data"] == (
        "0x2e567b36000000000000000000000000c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2000000000000000000000000a2e06c19ee14255889f0ec0ca37f6d0778d06754000000000000000000000000a2e06c19ee14255889f0ec0ca37f6d0778d067540000000000000000000000000000000000000000000000000853a0d2313c000000000000000000000000000000000000000000000000000000000000000000a000000000000000000000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000000000000000000040000000000000000000000000000000000000000000000000000000000000006000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    ), "incorrect data on message_data"
    assert (
        msg.retryable_creation_id == "0x8ba13904639c7444d8578cc582a230b8501c9f0f7903f5069d276fdd3a7dea44"
    ), "incorrect retryable creation id"


def test_does_call_for_classic_events():
    # Receipt from mainnet tx: 0xc80e0c4844bb502ed7d7e2db6f9e6b2d52e3d25688de216394f0227fc5dc814e
    receipt = {
        "to": HexBytes("0x4Dbd4fc535Ac27206064B68FfCf827b0A60BAB3f"),
        "from": HexBytes("0xA928c403Af1993eB309451a3559F8946E7d81F7F"),
        "contractAddress": None,
        "transactionIndex": 0,
        "gasUsed": 0,
        "logsBloom": HexBytes(
            "0x00000000000000000000000000000000000000000000000000000000000040000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000000000000000000000000008000000000002000000000000000008000000000000000000000000000000000000020000000000000000000000000000000000010200000000000000000000000000000800000100000000000000008010001000000000000000000000000000000000000000000000000000000100000000000000000000000000000000000001000000000000000200000000000000000000000000000000000000000800000000000004000"
        ),
        "blockHash": HexBytes("0x8c6512df3bc8d8422c9a345ee2c1e822f1538e0a00f1a02ac1a366ef57c7e561"),
        "transactionHash": HexBytes("0xc80e0c4844bb502ed7d7e2db6f9e6b2d52e3d25688de216394f0227fc5dc814e"),
        "logs": [
            {
                "transactionIndex": 122,
                "blockNumber": 14602546,
                "transactionHash": HexBytes("0xc80e0c4844bb502ed7d7e2db6f9e6b2d52e3d25688de216394f0227fc5dc814e"),
                "address": HexBytes("0x011B6E24FfB0B5f5fCc564cf4183C5BBBc96D515"),
                "topics": [
                    HexBytes("0x23be8e12e420b5da9fb98d8102572f640fb3c11a0085060472dfc0ed194b3cf7"),
                    HexBytes("0x0000000000000000000000000000000000000000000000000000000000064371"),
                    HexBytes("0x94ae25e1b4f5045af1c19d6bbb513dc9caad7f3986531c898d1e621b61d84341"),
                ],
                "data": HexBytes(
                    "0x0000000000000000000000004dbd4fc535ac27206064b68ffcf827b0a60bab3f00000000000000000000000000000000000000000000000000000000000000090000000000000000000000009817c403af1993eb309451a3559f8946e7d80e6ee205287f448301fa8583e565d955811fd3f296597965592f99e8c282094e32f1"
                ),
                "logIndex": 242,
                "blockHash": HexBytes("0x8c6512df3bc8d8422c9a345ee2c1e822f1538e0a00f1a02ac1a366ef57c7e561"),
                "removed": False,
            },
            {
                "transactionIndex": 122,
                "blockNumber": 14602546,
                "transactionHash": HexBytes("0xc80e0c4844bb502ed7d7e2db6f9e6b2d52e3d25688de216394f0227fc5dc814e"),
                "address": HexBytes("0x4Dbd4fc535Ac27206064B68FfCf827b0A60BAB3f"),
                "topics": [
                    HexBytes("0xff64905f73a67fb594e0f940a8075a860db489ad991e032f48c81123eb52d60b"),
                    HexBytes("0x0000000000000000000000000000000000000000000000000000000000064371"),
                ],
                "data": HexBytes(
                    "0x00000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000000000000000120000000000000000000000000a928c403af1993eb309451a3559f8946e7d81f7f0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000063eb89da4ed00000000000000000000000000000000000000000000000000000000002c912972d8000000000000000000000000a928c403af1993eb309451a3559f8946e7d81f7f000000000000000000000000a928c403af1993eb309451a3559f8946e7d81f7f000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
                ),
                "logIndex": 243,
                "blockHash": HexBytes("0x8c6512df3bc8d8422c9a345ee2c1e822f1538e0a00f1a02ac1a366ef57c7e561"),
                "removed": False,
            },
        ],
        "cumulativeGasUsed": 0,
        "blockNumber": 14602546,
        "confirmations": 1279492,
        "effectiveGasPrice": 0,
        "byzantium": True,
        "type": 2,
        "status": 1,
    }

    rpc_url = "https://arb1.arbitrum.io/rpc"
    arb_provider = Web3(HTTPProvider(rpc_url))
    parent_txn_receipt = ParentTransactionReceipt(receipt)

    tx_receipt = None
    try:
        # Try getting nitro messages using a classic tx
        tx_receipt = parent_txn_receipt.get_parent_to_child_messages(arb_provider)
    except Exception as err:
        # This call should throw an error
        assert isinstance(err, Exception)
        assert (
            str(err)
            == "This method is only for nitro transactions. Use 'get_parent_to_child_messages_classic' for classic transactions."
        )
    finally:
        # Should not successfully get nitro messages
        assert tx_receipt is None, "Nitro method was successful using a classic transaction."

    is_classic = parent_txn_receipt.is_classic(arb_provider)
    msg = (parent_txn_receipt.get_parent_to_child_messages_classic(arb_provider))[0]
    status = msg.status()

    assert is_classic, "incorrect tx type returned by isClassic call"
    assert status == ParentToChildMessageStatus.EXPIRED, "invalid message status"
    assert msg.message_number == 0x064371, "incorrect message number"
    assert (
        msg.retryable_creation_id == "0xc88b1821af42b8281bbf645173e287e4ec50ef96907f5211dc7069e09af20720"
    ), "incorrect retryable creation id"
    assert (
        msg.auto_redeem_id == "0x38c5c31151344c7a1433a849bbc80472786ebe911630255a6e25d6a2efd39526"
    ), "incorrect auto redeem id"
    assert (
        msg.child_tx_hash == "0xf91e7d2e7526927e915a2357360a3f1108dce0f9c7fa88a7492669adf5c1e53b"
    ), "incorrect child tx hash"
