import os
import dotenv

# Construct the path to the .env file
current_file_path = os.path.realpath(__file__)
scripts_directory = os.path.dirname(current_file_path)  # Path of src/scripts
src_directory = os.path.dirname(scripts_directory)  # Path of src
project_directory = os.path.dirname(src_directory)  # Root of the project

env_path = os.path.join(project_directory, ".env")

# Load the .env file
dotenv.load_dotenv(dotenv_path=env_path)


from web3 import Web3, HTTPProvider
import json
from src.scripts.test_setup import setup_networks, config, get_signer
import os


def main():
    # eth_provider = Web3(HTTPProvider(config["ETH_URL"]))
    # arb_provider = Web3(HTTPProvider(config["ARB_URL"]))

    # eth_deployer = get_signer(eth_provider, config["ETH_KEY"])
    # arb_deployer = get_signer(arb_provider, config["ARB_KEY"])

    l1_network, l2_network = setup_networks(
        l1_private_key=config['ETH_KEY'], l2_private_key=config['ARB_KEY'], l1_url=config["ETH_URL"], l2_url=config["ARB_URL"]
    )

    with open("localNetwork.json", "w") as f:
        json.dump({"l1Network": l1_network, "l2Network": l2_network}, f, indent=2)
        print("localNetwork.json updated")


if __name__ == "__main__":
    main()
    print("Done.")
