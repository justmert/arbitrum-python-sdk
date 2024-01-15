import os
import dotenv
from src.scripts import PROJECT_DIRECTORY

# Construct the path to the .env file
# current_file_path = os.path.realpath(__file__)
# scripts_directory = os.path.dirname(current_file_path)  # Path of src/scripts
# src_directory = os.path.dirname(scripts_directory)  # Path of src
# project_directory = os.path.dirname(src_directory)  # Root of the project
import asyncio

env_path = os.path.join(PROJECT_DIRECTORY, ".env")

# Load the .env file
dotenv.load_dotenv(dotenv_path=env_path)


from web3 import Web3, HTTPProvider
import json
from src.scripts.test_setup import setup_networks, config, get_signer
import os
from web3.middleware import geth_poa_middleware


async def main():

    eth_provider = Web3(HTTPProvider(config['ETH_URL']))
    arb_provider = Web3(HTTPProvider(config['ARB_URL']))

    # Adjust for PoA middleware if necessary
    eth_provider.middleware_onion.inject(geth_poa_middleware, layer=0)
    arb_provider.middleware_onion.inject(geth_poa_middleware, layer=0)

    # Create signers for deployments
    l1_deployer = get_signer(eth_provider, config['ETH_KEY'])
    l2_deployer = get_signer(arb_provider, config['ARB_KEY'])

    networks_and_deployers = await setup_networks(
        l1_deployer=l1_deployer, l2_deployer=l2_deployer, l1_url=config["ETH_URL"], l2_url=config["ARB_URL"], l1_provider=eth_provider, l2_provider=arb_provider
    )

    l1_network = networks_and_deployers["l1Network"].to_dict()
    l2_network = networks_and_deployers["l2Network"].to_dict()
    
    with open("localNetwork.json", "w") as f:
        json.dump({"l1Network": l1_network, "l2Network": l2_network}, f, indent=2)
        print("localNetwork.json updated")


if __name__ == "__main__":
    asyncio.run(main())
    print("Done.")
