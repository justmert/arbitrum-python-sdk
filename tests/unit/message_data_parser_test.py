import pytest
from web3 import Web3
from eth_utils import to_checksum_address, big_endian_to_int

from src.lib.message.message_data_parser import SubmitRetryableMessageDataParser  # Replace with actual import

def test_does_parse_l1_to_l2_message():
    message_data_parser = SubmitRetryableMessageDataParser()
    # Test data from the JavaScript test
    retryable_data = '0x000000000000000000000000467194771DAE2967AEF3ECBEDD3BF9A310C76C650000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000030346F1C785E00000000000000000000000000000000000000000000000000000053280CF1490000000000000000000000007F869DC59A96E798E759030B3C39398BA584F0870000000000000000000000007F869DC59A96E798E759030B3C39398BA584F08700000000000000000000000000000000000000000000000000000000000210F100000000000000000000000000000000000000000000000000000000172C586500000000000000000000000000000000000000000000000000000000000001442E567B360000000000000000000000006B175474E89094C44DA98B954EEDEAC495271D0F0000000000000000000000007F869DC59A96E798E759030B3C39398BA584F0870000000000000000000000007F869DC59A96E798E759030B3C39398BA584F08700000000000000000000000000000000000000000000003871022F1082344C7700000000000000000000000000000000000000000000000000000000000000A000000000000000000000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000000000000000000040000000000000000000000000000000000000000000000000000000000000006000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'

    res = message_data_parser.parse(retryable_data)

    assert res['callValueRefundAddress'] == '0x7F869dC59A96e798e759030b3c39398ba584F087'
    assert res['data'] == '0x2E567B360000000000000000000000006B175474E89094C44DA98B954EEDEAC495271D0F0000000000000000000000007F869DC59A96E798E759030B3C39398BA584F0870000000000000000000000007F869DC59A96E798E759030B3C39398BA584F08700000000000000000000000000000000000000000000003871022F1082344C7700000000000000000000000000000000000000000000000000000000000000A000000000000000000000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000000000000000000040000000000000000000000000000000000000000000000000000000000000006000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
    assert res['destAddress'] == '0x467194771dAe2967Aef3ECbEDD3Bf9a310C76C65'
    assert res['excessFeeRefundAddress'] == '0x7F869dC59A96e798e759030b3c39398ba584F087'
    assert Web3.toHex(Web3.toBytes(res['gasLimit'])) == '0x0210f1'
    assert Web3.toHex(Web3.toBytes(res['l1Value'])) == '0x30346f1c785e'
    assert res['l2CallValue'] == 0
    assert Web3.toHex(Web3.toBytes(res['maxFeePerGas'])) == '0x172c5865'
    assert Web3.toHex(Web3.toBytes(res['maxSubmissionFee'])) == '0x53280cf149'

def test_does_parse_eth_deposit_in_l1_to_l2_message():
    message_data_parser = SubmitRetryableMessageDataParser()
    # Test data from the JavaScript test
    retryable_data = '0x000000000000000000000000F71946496600E1E1D47B8A77EB2F109FD82DC86A0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001A078F0000D790000000000000000000000000000000000000000000000000000000000370E285A0C000000000000000000000000F71946496600E1E1D47B8A77EB2F109FD82DC86A000000000000000000000000F71946496600E1E1D47B8A77EB2F109FD82DC86A000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'

    res = message_data_parser.parse(retryable_data)
    assert res['callValueRefundAddress'] == '0xf71946496600e1e1d47b8A77EB2f109Fd82dc86a'
    assert res['data'] == '0x'
    assert res['destAddress'] == '0xf71946496600e1e1d47b8A77EB2f109Fd82dc86a'
    assert res['excessFeeRefundAddress'] == '0xf71946496600e1e1d47b8A77EB2f109Fd82dc86a'
    assert res['gasLimit'] == 0
    
    expected_l1_value_wei = Web3.toWei('30.01', 'ether')
    assert int(Web3.toHex(Web3.toBytes(res['l1Value'])), 16) == int(expected_l1_value_wei)


    assert res['l2CallValue'] == 0
    assert res['maxFeePerGas'] == 0
    assert Web3.toHex(Web3.toBytes(res['maxSubmissionFee'])) == '0x370e285a0c'