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
from pathlib import Path
from typing import List, Optional, Union

import yaml
from jaeger_client import Config

from prism.common.config import init_config, configuration
from prism.common.config.config import load_dict_config
from prism.common.epoch.genesis import GenesisInfo, NeighborInfo
from prism.common.logging import init_logging, configure_logging
from prism.common.replay import Replay
from prism.common.transport.enums import LinkType
from prism.rib.Log import logError, logWarning, logDebug
from prism.rib.common import CHECKSUM_BYTES
from prism.rib.connection.CommsTransport import CommsTransport
from prism.rib.connection.profiles import load_profiles
from prism.rib.state import RIBStateStore
from networkManagerPluginBindings import IRacePluginNM, PLUGIN_OK, IRaceSdkNM, EncPkg, PluginConfig, PLUGIN_FATAL


class SRINMPlugin(IRacePluginNM):
    def __init__(self, sdk: IRaceSdkNM = None):
        super().__init__()

        self.raceSdk = sdk
        self.configuration = configuration
        self.state_store = RIBStateStore(sdk)

        # Override this in subclasses to point to the submodule of prism that is primarily in play,
        # e.g. "client" or "server". It determines logging configuration and which config files will
        # be loaded.
        self.plugin_type = "common"

        self.platform_config_path = None
        self.log_path = None
        self.race_persona = sdk.getActivePersona()
        self.race_personas = {}

        self.replay = None
        self.transport: Optional[CommsTransport] = None

    #####
    # Plugin API Methods
    #####

    def init(self, config: PluginConfig) -> int:
        init_logging()

        self.log_path = Path(config.loggingDirectory) / "prism"
        self.log_path.mkdir(parents=True, exist_ok=True)

        init_config(json.dumps(self.prism_config()), [])

        for config_type in ["prism", "server", "client", self.race_persona, "bootstrap"]:
            self.load_race_config(config_type)

        module_name = f"prism.{self.plugin_type}"
        configure_logging(module_name, self.configuration)
        self.configure_jaeger(Path(config.etcDirectory) / "jaeger-config.yml")

        self.replay = Replay(self.race_persona, self.log_path, checksum_bytes=CHECKSUM_BYTES)
        self.transport = CommsTransport(
            self.configuration,
            self.raceSdk,
            self.replay,
        )

        return self.start()

    def start(self) -> int:
        try:
            self.replay.start()
            self.transport.start()
        except:
            import traceback
            logError(traceback.format_exc())
            return PLUGIN_FATAL
        return PLUGIN_OK

    def shutdown(self) -> int:
        self.transport.shutdown()
        self.replay.stop()
        return PLUGIN_OK

    def processEncPkg(self, handle: int, pkg: EncPkg, conn_ids: List[str]) -> int:
        return self.transport.processEncPkg(handle, pkg, conn_ids)

    def onConnectionStatusChanged(self, handle, conn_id, status, link_id, properties) -> int:
        return self.transport.onConnectionStatusChanged(handle, conn_id, status, link_id, properties)

    def onPackageStatusChanged(self, handle, status) -> int:
        return self.transport.onPackageStatusChanged(handle, status)

    def onPersonaLinksChanged(self, recipient_persona, link_type, links) -> int:
        return PLUGIN_OK

    def onLinkPropertiesChanged(self, link_id, link_properties) -> int:
        return self.transport.onLinkPropertiesChanged(link_id, link_properties)

    def onLinkStatusChanged(self, handle, link_id, status, properties) -> int:
        return self.transport.onLinkStatusChanged(handle, link_id, status, properties)

    def onChannelStatusChanged(self, handle, channel_id, status, properties) -> int:
        return self.transport.onChannelStatusChanged(handle, channel_id, status, properties)

    def onUserInputReceived(self, handle, answered, response) -> int:
        logDebug(f"User input received: {response}")
        return PLUGIN_OK

    def onUserAcknowledgementReceived(self, handle):
        return PLUGIN_OK

    #####
    # Bootstrapping
    #####

    def prepareToBootstrap(self, handle, link_id, config_out_path, device_info):
        return PLUGIN_OK

    def onBootstrapPkgReceived(self, persona, pkg):
        return PLUGIN_OK

    #####
    # Epoch Change
    #####

    def notifyEpoch(self, data: str):
        return PLUGIN_OK

    #####
    # Setup/Cleanup Methods
    #####

    def load_race_config(self, filename):
        config_dict = self.load_config_file(f"{filename}.json")
        if not config_dict:
            return
        logDebug(f"Loading config from {filename}.json")
        load_dict_config(config_dict)

    def read_text(self, filename: Union[str, Path]) -> Optional[str]:
        data = self.raceSdk.readFile(str(filename))
        if not data:
            return None
        return bytes(data).decode("utf-8")

    def write_text(self, filename: Union[str, Path], text: str):
        self.raceSdk.writeFile(str(filename), text.encode("utf-8"))

    def load_config_file(self, filename) -> dict:
        path = Path(filename)
        logDebug(f"Attempting to load config file {filename}")
        text = self.read_text(path)
        logDebug(f"Loaded text: {text}")

        if not text:
            logWarning(f"Warning: Could not read config file {filename}.")
            return {}

        if path.suffix == ".json":
            return json.loads(text)
        elif path.suffix == ".yml":
            return yaml.safe_load(text)
        else:
            logWarning(f"Tried to load file with unknown extension: {filename}")

    def configure_jaeger(self, jaeger_config_path: Path):
        jaeger_disabled_config = Config(config={"disabled": True}, service_name=self.race_persona)

        try:
            logDebug(f"Reading Jaeger config from {jaeger_config_path}")
            config = yaml.safe_load(jaeger_config_path.read_text())
            if "reporter" not in config:
                logError("No jaeger config available")
                jaeger_disabled_config.initialize_tracer()
                return

            reporter_config = config["reporter"]
            if "localAgentHostPort" in reporter_config:
                host, port = config["reporter"]["localAgentHostPort"].split(":")
                self.configuration["jaeger_agent_host"] = host
                self.configuration["jaeger_agent_port"] = port
            if "endpoint" in reporter_config:
                self.configuration["jaeger_endpoint"] = reporter_config["endpoint"]

            jaeger_config = Config(config, service_name=self.race_persona)
        except OSError as e:
            logError("Failed to open Jaeger Config: " + str(e))
            jaeger_disabled_config.initialize_tracer()
            return

        jaeger_config.initialize_tracer()

    def prism_config(self) -> dict:
        """Any JSON config parameters the plugin should pass to the PRISM component."""
        return {
            "name": self.race_persona,
            "debug": True,  # global config; could be overridden per persona config
            "production": False,  # enables Jaeger
            "log_dir": str(self.log_path.resolve()),
        }

    def configure_genesis(self) -> GenesisInfo:
        logDebug("Loading genesis configuration")
        neighbors = [NeighborInfo.from_dict(d) for d in self.load_config_file("neighborhood.json")]
        neighbor_names = {neighbor.name for neighbor in neighbors}
        logDebug(f"Loaded neighbors {neighbor_names}")

        logDebug("Loading link profiles")
        profiles = load_profiles(self.raceSdk)
        logDebug(f"Loaded profiles for {len(profiles)} channels")

        send_links = []
        broadcast_links = []
        receive_links = []

        if configuration.is_client:
            for channel, profiles in profiles.items():
                for profile in profiles:
                    if profile.link_type.can_recv:
                        receive_links.append(profile)
                    else:
                        send_links.append(profile)
        else:
            for channel, profiles in profiles.items():
                for profile in profiles:
                    if profile.link_type == LinkType.RECV:
                        receive_links.append(profile)
                    elif set(profile.personas).issubset(neighbor_names):
                        send_links.append(profile)
                    else:
                        broadcast_links.append(profile)

        logDebug("Categorized links")

        genesis_info = GenesisInfo(
            neighbors=neighbors,
            send_links=send_links,
            broadcast_links=broadcast_links,
            receive_links=receive_links,
        )

        logDebug(f"{genesis_info}")

        return genesis_info
