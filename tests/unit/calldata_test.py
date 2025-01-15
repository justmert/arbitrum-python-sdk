import pytest
from eth_typing import HexStr

from arbitrum_py.utils.calldata import (
    get_erc20_parent_address_from_parent_to_child_tx_request,
)


class TestCalldata:
    class TestGetErc20ParentAddressFromParentToChildTxRequest:
        def test_decodes_outbound_transfer_calldata(self):
            """Test decoding calldata from outboundTransfer method call"""
            calldata = "0xd2ce7d65000000000000000000000000c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2000000000000000000000000df7fa906da092cc30f868c5730c944f4d5431e17000000000000000000000000000000000000000000000000dea56a0c808e9b6a0000000000000000000000000000000000000000000000000000000000026257000000000000000000000000000000000000000000000000000000000393870000000000000000000000000000000000000000000000000000000000000000c000000000000000000000000000000000000000000000000000000000000000600000000000000000000000000000000000000000000000000000580cedab294000000000000000000000000000000000000000000000000000000000000000400000000000000000000000000000000000000000000000000000000000000000"
            expected_address = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"

            # Create mock tx request
            mock_request = {"txRequest": {"data": HexStr(calldata)}}

            output = get_erc20_parent_address_from_parent_to_child_tx_request(mock_request)
            assert output == expected_address

        def test_decodes_outbound_transfer_custom_refund_calldata(self):
            """Test decoding calldata from outboundTransferCustomRefund method call"""
            calldata = "0x4fb1a07b000000000000000000000000429881672b9ae42b8eba0e26cd9c73711b891ca50000000000000000000000000f571d2625b503bb7c1d2b5655b483a2fa696fef0000000000000000000000007ecc7163469f37b777d7b8f45a667314030ace240000000000000000000000000000000000000000000000000de0b6b3a764000000000000000000000000000000000000000000000000000000000000000186a00000000000000000000000000000000000000000000000000000000011e1a30000000000000000000000000000000000000000000000000000000000000000e000000000000000000000000000000000000000000000000000000000000000600000000000000000000000000000000000000000000000000000e35fa931a00000000000000000000000000000000000000000000000000000000000000000400000000000000000000000000000000000000000000000000000000000000000"
            expected_address = "0x429881672B9AE42b8EbA0E26cD9C73711b891Ca5"

            # Create mock tx request
            mock_request = {"txRequest": {"data": HexStr(calldata)}}

            output = get_erc20_parent_address_from_parent_to_child_tx_request(mock_request)
            assert output == expected_address

        def test_throws_on_bad_calldata(self):
            """Test handling invalid calldata"""
            calldata = "0xInvalidCalldata"

            with pytest.raises(Exception) as exc_info:
                get_erc20_parent_address_from_parent_to_child_tx_request({"txRequest": {"data": HexStr(calldata)}})
            assert str(exc_info.value) == "data signature not matching deposits methods"

        def test_throws_on_empty_string(self):
            """Test handling empty calldata string"""
            with pytest.raises(Exception) as exc_info:
                get_erc20_parent_address_from_parent_to_child_tx_request({"txRequest": {"data": HexStr("")}})

            assert str(exc_info.value) == "data signature not matching deposits methods"

        def test_throws_on_undefined_data(self):
            """Test handling undefined calldata"""
            with pytest.raises(Exception) as exc_info:
                get_erc20_parent_address_from_parent_to_child_tx_request({"txRequest": {"data": None}})

            assert str(exc_info.value) == "data signature not matching deposits methods"
