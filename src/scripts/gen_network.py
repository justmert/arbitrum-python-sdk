import asyncio
import json
import os

import dotenv
from web3 import HTTPProvider, Web3
from web3.middleware import construct_sign_and_send_raw_middleware, geth_poa_middleware

from src.lib.data_entities.signer_or_provider import SignerOrProvider
from src.scripts import PROJECT_DIRECTORY

env_path = os.path.join(PROJECT_DIRECTORY, ".env")
dotenv.load_dotenv(dotenv_path=env_path)

from src.scripts.test_setup import config, get_signer, setup_networks  # noqa: E402


async def main():
    eth_provider = Web3(HTTPProvider(config["ETH_URL"]))
    arb_provider = Web3(HTTPProvider(config["ARB_URL"]))

    eth_provider.middleware_onion.inject(geth_poa_middleware, layer=0)
    arb_provider.middleware_onion.inject(geth_poa_middleware, layer=0)

    l1_deployer = get_signer(eth_provider, config["ETH_KEY"])
    l2_deployer = get_signer(arb_provider, config["ARB_KEY"])

    eth_provider.middleware_onion.add(construct_sign_and_send_raw_middleware(l1_deployer))

    arb_provider.middleware_onion.add(construct_sign_and_send_raw_middleware(l2_deployer))

    l1_signer = SignerOrProvider(l1_deployer, eth_provider)
    l2_signer = SignerOrProvider(l2_deployer, arb_provider)

    networks_and_deployers = await setup_networks(
        l1_url=config["ETH_URL"],
        l2_url=config["ARB_URL"],
        l1_deployer=l1_signer,
        l2_deployer=l2_signer,
    )

    l1_network = networks_and_deployers["l1Network"].to_dict()
    l2_network = networks_and_deployers["l2Network"].to_dict()

    with open("localNetwork.json", "w") as f:
        json.dump({"l1Network": l1_network, "l2Network": l2_network}, f, indent=2)
        print("localNetwork.json updated")


if __name__ == "__main__":
    asyncio.run(main())
    print("Done.")
