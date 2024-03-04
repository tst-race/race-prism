#  Copyright (c) 2019-2023 SRI International.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
from __future__ import annotations

import ast
import json
from copy import copy, deepcopy
from dataclasses import dataclass, field
from json import JSONDecodeError
from pathlib import Path
from typing import Optional, Any, List

from prism.config.error import ConfigError

PRISM_DEFAULTS = {
    "pseudonym_salt": "PRISM",
    "production": False,
    "debug": True,
    "log_monitor_interval": 10,
    "max_plaintext_size": 2000,
    "max_message_size": 10000,
    "dropboxes_per_client": None,
    "dropbox_send_redundancy": None,
    "dropbox_poll_with_duration": True,
    "poll_timing_ms": 600000,
    "transport_send_timeout": 720,
    "transport_open_connection_timeout": 720,
    "mpc_modulus": 210340362182463027693671312934069294429519269866912637212799832923523392566897,
    "strict_channel_tags": True,
}

CLIENT_DEFAULTS = {
}

SERVER_DEFAULTS = {
    # Server ARKS batches can be at most this many bytes
    "cs2_arks_max_mtu": 100000,
    # Server ARKS batches are broadcast at intervals of this many seconds
    "cs2_ark_sleep_time": 60,
    # Servers update their own ARK at intervals of this many minutes
    "cs2_ark_timeout": 15.0,
    # ARKs expire after this multiple of cs2_ark_timeout
    "cs2_ark_expiration_factor": 10.0,
    # VRF defaults for smaller deployments ~10 servers:
    "vrf_p_off": 0.0,
    "vrf_p_emix": 0.3,
    "vrf_n_ranges": 1,
    "vrf_m_replicas": 1,
    "vrf_c_p_factor": 3.0,  # factor c for random link probabilities: p=c*ln(n)/n or p_i=c*ln(n)/(n*i) for b=0 or >0
    "vrf_b_db_emix": 2,     # two EMIXes per DB leader; if b=0 then induce ER random graph with uniform p=c*ln(n)/n;
                            # if b=-1 then use old clustering algorithm for topology (not VRF)
    "vrf_seed": 0,
    # False: spreads dropbox_indices over [0; (n_ranges * m_replicas) - 1]
    # True: uses dropbox_index := n_range - 1 and forces dropboxes_per_client := 1 to let replicas handle redundnacy
    "vrf_db_index_from_range_id": True,
}


@dataclass
class Configuration:
    """PRISM system parameters."""

    # Server (other than client registration committee and other special roles) role assignment
    # Defined in prism.common.vrf.sortition
    sortition: str = "STATIC"
    # If sortition == "STATIC" use these ratios to assign DROPBOX and EMIX roles:
    # The fraction of servers that should be single server dropboxes
    ss_dropbox_ratio: float = None
    # The fraction of servers that should be members of MPC Dropbox committees.
    mpc_dropbox_ratio: float = None
    # If sortition == "VRF" try this many times to get a viable sortition before giving up:
    vrf_config_attempts = 5
    # If sortition == "VRF" and this setting is True, then create single-server DROPBOX instead of MPC ones:
    vrf_dropbox_ss = False

    # The size of each MPC committee.
    mpc_committee_size: int = 4

    # Whether to disable control traffic and pregenerate ARKs/LSP
    control_traffic: bool = True
    preload_arks: bool = False

    # Configure a client registration committee server
    bootstrapping: bool = True

    # Which network topology to use.
    # Defined in prism.config.topology.topology
    topology: str = "CLUSTERED"

    # Create multicast links on channels that claim to support them
    multicast: bool = True

    # The maximum number of emixes to connect to each dropbox
    emixes_per_dropbox: int = 2
    # The maximum number of emixes to connect to each client
    emixes_per_client: int = 2
    # The number of emix clusters to create in the "CLUSTERED" topology.
    # 0 instructs the topology to pick a number
    emix_clusters: int = 0
    # If set to False then don't check if we have enough dropboxes in genesis epoch.
    strict_dropbox_count: bool = True

    # The number of onion layers clients should aim for. Will be
    # adjusted downward (with a warning) if there are not enough
    # servers assigned the EMIX role to meet the target.
    onion_layers: int = 3

    # The directory to look for cached IBE identities when running
    # in an environment where bfibe tooling is not available.
    ibe_dir: Optional[str] = None
    # The security level to run the IBE system at.
    # Defined in bfibe/src/security.c
    ibe_level: int = 3
    # The number of client registration servers to distribute IBE shards across, if bootstrapping is enabled
    ibe_shards: int = 1

    # Maximum channels per logical link
    direct_channel_choices: int = 1
    indirect_channel_choices: int = 1

    indirect_emix_to_emix: bool = False
    indirect_emix_to_dropbox: bool = False
    indirect_cluster_to_cluster: bool = False

    # Generate downlinks at genesis -- needed for CREATOR_TO_LOADER downlinks to function at genesis
    genesis_downlinks: bool = False
    genesis_uplinks: bool = False

    # Salt to use for server pseudonyms.
    server_pseudonym_salt: str = "PRISM"

    # Find a client pseudonym salt that evenly distributes clients across available dropboxes
    optimize_salt: bool = True

    # The common configuration parameters for clients and servers.
    # Will be augmented during configuration duration. You can override
    # it with e.g. -Pclient.poll_timing_ms=120000
    prism_common: dict = field(default_factory=lambda: copy(PRISM_DEFAULTS))
    client_common: dict = field(default_factory=lambda: copy(CLIENT_DEFAULTS))
    server_common: dict = field(default_factory=lambda: copy(SERVER_DEFAULTS))

    # A fixed random seed to use for stochastic elements of configuration, to
    # attempt to make config generation reproducible. Doesn't always work.
    random_seed: int = 1

    # if set to True then generate PKI infrastructure as config items and files
    pki: bool = True
    # if epochs = 0 then configure servers with Root Key (to generate self-signed server certs at runtime)
    # if epochs > 0 then generate pre-made server certificates and private keys to be saved as files
    # NOTE: epochs > 0 is not supported in any other deployments than Testbed!
    pki_epochs: int = 0

    # A copy of the input parameters are saved here before config generation is run
    frozen: Optional[dict] = None

    def update_field(self, fname, val) -> bool:
        if not hasattr(self, fname):
            return False

        current = getattr(self, fname)

        if isinstance(current, dict):
            if isinstance(val, dict):
                current.update(val)
            else:
                raise TypeError("dicts must be updated with other dicts")
        else:
            setattr(self, fname, val)

        return True

    @staticmethod
    def load_args(args) -> Configuration:
        config = Configuration()

        for f in args.json_configs:
            try:
                j = json.load(f)

                for k, v in j.items():
                    if not config.update_field(k, v):
                        print(f"Warning: JSON file {f.name} attempted to configure " f"field {k} which does not exist.")
            except JSONDecodeError:
                raise ConfigError(f"Error loading JSON config file {f.name}")

        for k, v in vars(args).items():
            if v is None:
                continue

            if hasattr(config, k):
                setattr(config, k, v)

        for override in args.param_overrides:
            config.override(override)

        return config

    def freeze(self):
        self.frozen = deepcopy(vars(self))
        del self.frozen["frozen"]

    def write(self, output_directory: Path):
        """Write the full configuration out to a file or files in the specified directory."""
        output_directory.mkdir(exist_ok=True, parents=True)
        with open(output_directory / "config_input.json", "w") as f:
            json.dump(self.frozen, f, indent=4)

    def get_path(self, path: List[str]) -> Any:
        try:
            attr = path[0]
            key_path = path[1:]

            target = getattr(self, attr)

            if len(path) > 1 and not isinstance(target, dict):
                raise ConfigError(
                    f"Config attribute {attr} is not a dictionary, and cannot be overridden with a key path."
                )

            for position, component in enumerate(key_path):
                if component not in target and position < len(key_path) - 1:
                    target[component] = {}
                target = target.get(component)
            return target
        except KeyError:
            return None
        except AttributeError:
            valid_settings = list(self.__dict__.keys())
            valid_settings.remove("frozen")
            raise ConfigError(
                f"{path[0]} is not a valid setting. Valid settings are {', '.join(valid_settings)}.\n"
                f"See {__file__} for more details."
            )

    def set_path(self, path: List[str], val: Any):
        if len(path) == 1:
            setattr(self, path[0], val)
            return

        target = getattr(self, path[0])
        for component in path[1:-1]:
            target = target[component]
        target[path[-1]] = val

    def override(self, override: str):
        k, v = override.split("=", 1)
        k_path = k.split(".")

        if k_path[0] in ["prism", "server", "client"]:
            k_path[0] = k_path[0] + "_common"

        default = self.get_path(k_path)

        if default is None:
            print(f"WARNING: Overriding {k}, which has no default. Double check that you have the correct name.")

        parsed_value = self.parse_config_value(v, default)
        if default is not None and type(default) != type(parsed_value):
            raise ConfigError(f"Expected a value of type {type(default).__name__} for config key path {k}")

        self.set_path(k_path, parsed_value)

    @staticmethod
    def parse_config_value(value: str, default):
        if value.lower() in ["true", "false"]:
            value = value.capitalize()

        try:
            parsed_value = ast.literal_eval(value)
        except ValueError:
            parsed_value = value

        # Coerce numeric types
        if isinstance(default, (int, float)) and isinstance(parsed_value, (int, float)):
            parsed_value = type(default)(parsed_value)

        return parsed_value
