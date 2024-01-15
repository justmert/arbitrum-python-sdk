from web3 import Web3
import re
from eth_abi import abi


error_data_hex = "0x07c266e3000000000000000000000000840bd0e55bf25bbc4861ba9eff53004e2aee93a7000000000000000000000000763d253a4f76299ac76369cc0416a5961c236d770000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000200000000000000000000000000000000000000000000000000000000000000010000000000000000000000003f1eae7d46d88f08fc2f8ed27fcb2ab183eb2d0e0000000000000000000000003f1eae7d46d88f08fc2f8ed27fcb2ab183eb2d0e00000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000000000000000014000000000000000000000000000000000000000000000000000000000000000c44201f9850000000000000000000000000000000000000000000000000000000000000040000000000000000000000000000000000000000000000000000000000000008000000000000000000000000000000000000000000000000000000000000000010000000000000000000000003a79b477768c0935daf987b4e7d69ebcc8afbacb00000000000000000000000000000000000000000000000000000000000000010000000000000000000000009ddeba87fb9c49258316e4454f49b578c180e6be00000000000000000000000000000000000000000000000000000000" 

# The error data in hexadecimal format

# def decode_error_data(hex_data, abi_types):
    # if hex_data.startswith("0x"):
    #     hex_data = hex_data[2:]
    
    # # Decode the data based on the ABI types
    # decoded_data = Web3().eth.abi.decode_parameters(abi_types, hex_data)
    # return decoded_data
# error_data_hex = "0x07c266e3..."  # Your error data
abi_types = ['address', 'address', 'uint256', 'uint256', 'uint256', 'address', 'address', 'uint256', 'uint256', 'bytes']

#   'error RetryableData(address from, address to, uint256 l2CallValue, uint256 deposit, uint256 maxSubmissionCost, address excessFeeRefundAddress, address callValueRefundAddress, uint256 gasLimit, uint256 maxFeePerGas, bytes data)',


# Remove '0x' prefix and skip the first 4 bytes (8 characters)
if error_data_hex.startswith("0x"):
    error_data_hex = error_data_hex[2:]
error_data_hex = error_data_hex[8:]

# Decode the error data
decoded_data = abi.decode(abi_types, bytes.fromhex(error_data_hex))

# Print the decoded data
for i, data in enumerate(decoded_data):
    if isinstance(data, bytes):
        # byte to hex
        print('hex', data.hex())
    else:
        print(f"Parameter {i+1} ({abi_types[i]}):", data)

