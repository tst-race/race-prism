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
import json
import shutil
from pathlib import Path
from typing import List, Optional

from prism.config.config import Configuration
from prism.config.environment.deployment import Deployment
from prism.config.environment.pki_files import generate_pki, create_server_file
from prism.config.error import ConfigError
from prism.config.node.client import Client
from prism.config.node.node import Node
from prism.config.node.server import Server, Emix, Dropbox
from prism.config.topology.graph import can_draw, draw_graph

from .channel import Channel
from .link_negotiation import generate_link_requests, generation_status
from .range import RIBRange
from .test_plan import generate_test_plan

PLUGIN_NAME = "prism"


class RIBDeployment(Deployment):
    channels: Optional[List[Channel]]

    def __init__(
        self, name=None, mode="local", config_file=None, output_path=None, channels_path=None, fulfilled_links_path=None
    ):
        if name:
            self.base = Path(Path.home(), ".race", "rib", "deployments", mode, name)
            self.config_path = self.base.joinpath("configs")
            self.config_file_path = self.config_path.joinpath("race-config.json")

        if config_file:
            self.config_file_path = Path(config_file)

        if not self.config_file_path.exists():
            raise ConfigError("Deployment not found.")

        self.race_config = json.loads(self.config_file_path.read_text())

        if channels_path:
            channels_path = Path(channels_path)
            self.channels = [Channel.from_json(j) for j in json.loads(channels_path.read_text())]
        else:
            self.channels_path = None
            self.channels = None

        if output_path:
            self.output_path = Path(output_path)
        else:
            self.output_path = self.config_path.joinpath("network-manager", PLUGIN_NAME)

        self.link_requests_path = self.output_path.joinpath("network-manager-request.json")
        self.persona_path = self.output_path.joinpath("personas")
        self.committee_path = self.output_path.joinpath("committees")
        self.status_path = self.output_path.joinpath("network-manager-config-gen-status.json")
        self.range = RIBRange(self.race_config)

        if fulfilled_links_path:
            fulfilled_links_path = Path(fulfilled_links_path)
            self.fulfilled_links = json.loads(fulfilled_links_path.read_text())
            self.requested_links = json.loads(self.link_requests_path.read_text())
        else:
            self.requested_links = None
            self.fulfilled_links = {}

    def committee(self, node: Node) -> dict:
        if isinstance(node, Client):
            return self.client_committee(node)
        elif isinstance(node, Server):
            return self.server_committee(node)

    @staticmethod
    def client_committee(client: Client) -> dict:
        return {
            "entranceCommittee": sorted(
                [node.name for node in client.linked if isinstance(node, Server) and node.is_role(Emix)]
            ),
            "dropboxes": sorted(
                [node.name for node in client.tags.get("dropboxes", [])]
            ),
        }

    @staticmethod
    def server_committee(server: Server) -> dict:
        def intra_committee(other):
            mpc_committee = server.tags.get("mpc_committee")
            other_committee = other.tags.get("mpc_committee")
            return mpc_committee is not None and mpc_committee == other_committee

        if server.is_role(Dropbox):
            clients = [node.name for node in server.tags.get("db_clients", [])]
        else:
            clients = [node.name for node in server.linked if node.client_ish]

        return {
            "reachableClients": sorted(clients),
            "reachableIntraCommitteeServers": sorted(
                [node.name for node in server.linked
                 if isinstance(node, Server) and intra_committee(node)]
            ),
            "reachableInterCommitteeServers": sorted(
                [node.name for node in server.linked
                 if isinstance(node, Server) and not intra_committee(node) and not node.client_ish]
            ),
        }

    def server_neighborhood(self, config: Configuration, server: Server):
        def tag(a: Server, b: Server):
            if a.is_role(Dropbox) and b.is_role(Dropbox):
                return "mpc"
            else:
                return "lsp"

        neighbors = [node for node in server.linked if isinstance(node, Server) and not node.client_ish]
        return [
            {
                "name": neighbor.name,
                "pseudonym": str(neighbor.pseudonym(config)),
                "public_key": neighbor.ark_key.encode().hex(),
                "tag": tag(server, neighbor)
            }
            for neighbor in neighbors
        ]

    def client_neighborhood(self, config: Configuration, client: Node):
        return [
            {
                "name": neighbor.name,
                "pseudonym": str(neighbor.pseudonym(config)),
                "tag": "emix" if neighbor.is_role(Emix) else "dropbox",
            }
            for neighbor in client.linked if isinstance(neighbor, Server)
        ]

    def neighborhood(self, config: Configuration, node: Node):
        if node.client_ish:
            return self.client_neighborhood(config, node)
        elif isinstance(node, Server):
            return self.server_neighborhood(config, node)

    def save(self, config: Configuration):
        root_pair, epoch_prefixes = generate_pki(config)

        if config.preload_arks:
            from prism.config.control_cache import ControlCache
            control_cache = ControlCache(self.range, config)
        else:
            control_cache = None

        for node in self.range.nodes.values():
            node_path = self.output_path / node.name
            node_path.mkdir()

            def write_json(filename, obj):
                node_path.joinpath(filename).write_text(json.dumps(obj, indent=2))

            if control_cache:
                cache_dir = node_path / "cache"
                cache_dir.mkdir()
                control_cache.write_for(cache_dir, node)

            write_json(f"{node.name}.json", node.config(config))
            write_json("committee.json", self.committee(node))
            write_json("prism.json", config.prism_common)
            write_json("neighborhood.json", self.neighborhood(config, node))

            if node.client_ish:
                write_json("client.json", config.client_common)
            if isinstance(node, Server):
                for epoch_prefix in epoch_prefixes:
                    # if we have PKI, create key, cert pair files for this server in all anticipated epochs
                    create_server_file(root_pair, node_path, f"{epoch_prefix}_{node.name}")
                write_json("server.json", config.server_common)

        link_requests = self.link_requests(config)
        if link_requests:
            self.write_json(self.link_requests_path, link_requests)
            status = generation_status(self.status_path, False, "Requesting links")
            self.write_json(self.status_path, status)

        # Write out a test plan
        self.write_json(self.output_path / "network-manager-test-plan.json", generate_test_plan(self.range))

        # Save our inputs for later reproduction
        config.write(self.output_path / "input")
        shutil.copy(self.config_file_path, self.output_path / "input" / "race-config.json")

        # Draw pretty pictures
        if can_draw(self.range):
            draw_graph(self.range.graph, self.output_path / "graph.ps")

    def check(self, config: Configuration) -> List[ConfigError]:
        errors = super().check(config)
        if config.pki_epochs > 0:
            errors.append(ConfigError(f"Cannot run RiB deployments with pki_epochs={config.pki_epochs} (> 0)"))
        return errors

    def link_requests(self, config: Configuration) -> Optional[dict]:
        if self.channels:
            missing_tags = Channel.missing_tags(self.channels)
            if missing_tags and config.prism_common.get("strict_channel_tags"):
                raise ConfigError(f"strict_channel_tags has been enabled, and "
                                  f"there are no tagged channels for tags: {missing_tags}")

            return generate_link_requests(self.range.links, self.channels, config)
        else:
            return None

    def mkdirs(self):
        super().mkdirs()
        self.persona_path.mkdir(exist_ok=True, parents=True)
        self.committee_path.mkdir(exist_ok=True, parents=True)

    def write_status(self, status):
        self.status_path.write_text(json.dumps(status, indent=2))
