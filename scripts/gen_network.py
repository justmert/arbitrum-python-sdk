import json
import os
import subprocess
from typing import Dict, Optional, Any
from dataclasses import asdict
import dotenv
from web3 import Web3, HTTPProvider
from eth_typing import URI

from arbitrum_py.data_entities.networks import map_l2_network_to_arbitrum_network
from arbitrum_py.utils.helper import CaseDict, load_contract
from arbitrum_py import PROJECT_DIRECTORY

env_path = os.path.join(PROJECT_DIRECTORY, ".env")
dotenv.load_dotenv(dotenv_path=env_path)


def get_local_networks_from_container(which: str) -> Dict[str, Any]:
    """Get networks configuration from Docker container"""
    docker_names = [
        "nitro_sequencer_1",
        "nitro-sequencer-1",
        "nitro-testnode-sequencer-1",
        "nitro-testnode_sequencer_1",
    ]

    for docker_name in docker_names:
        try:
            result = subprocess.run(
                ["docker", "exec", docker_name, "cat", f"/tokenbridge-data/{which}_network.json"],
                capture_output=True,
                text=True,
                check=True,
            )
            return json.loads(result.stdout)
        except subprocess.CalledProcessError:
            continue

    raise RuntimeError("nitro-testnode sequencer not found")


def patch_networks(
    l2_network: Dict[str, Any],
    l3_network: Optional[Dict[str, Any]] = None,
    l2_provider: Optional[Web3] = None,
) -> Dict[str, Any]:
    """
    The container's files are written by the token bridge deployment step of
    the test node, which runs a script in token-bridge-contracts.
    Once the script in token-bridge-contracts repo uses an sdk version with
    the same types and is updated to populate those fields, we can remove this patchwork
    """
    patched_l2_network = map_l2_network_to_arbitrum_network(l2_network)

    # native token for l3
    if l3_network and l2_provider:
        patched_l3_network = map_l2_network_to_arbitrum_network(l3_network)

        try:
            bridge_contract = load_contract(
                provider=l2_provider,
                contract_name="IERC20Bridge",
                address=l3_network["ethBridge"]["bridge"],
            )
            native_token = bridge_contract.functions.nativeToken().call()
            patched_l3_network["nativeToken"] = native_token
        except Exception:
            # l3 network doesn't have a native token
            pass

        return {"patchedL2Network": patched_l2_network, "patchedL3Network": patched_l3_network}

    return {"patchedL2Network": patched_l2_network}


def main():
    # Remove existing file if present
    try:
        os.remove("localNetwork.json")
    except OSError:
        pass

    output = get_local_networks_from_container("l1l2")
    # Check if testing orbit chains
    is_testing_orbit_chains = os.getenv("ORBIT_TEST") == "1"

    if is_testing_orbit_chains:

        # When running with L3 active, the container calls the L3 network L2
        # so we rename it here
        l2l3_networks = get_local_networks_from_container("l2l3")
        l3_network = l2l3_networks.get("l2Network")

        arb_url = os.getenv("ARB_URL")
        if not arb_url:
            raise ValueError("ARB_URL environment variable not set")

        l2_provider = Web3(HTTPProvider(URI(arb_url)))

        patched_networks = patch_networks(
            l2_network=output["l2Network"], l3_network=l3_network, l2_provider=l2_provider
        )

        output = {
            "l2Network": patched_networks["patchedL2Network"],
            "l3Network": patched_networks["patchedL3Network"],
        }

    else:
        patched_networks = patch_networks(l2_network=output["l2Network"])
        output["l2Network"] = patched_networks["patchedL2Network"]

    json_ready_output = CaseDict(output)

    # Write updated configuration
    with open("localNetwork.json", "w") as f:
        json.dump(json_ready_output.to_dict(), f, indent=2)

    print("localNetwork.json updated")


if __name__ == "__main__":
    main()
    print("Done.")
