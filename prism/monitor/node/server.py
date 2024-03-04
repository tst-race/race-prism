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
from datetime import datetime

from prism.monitor.reader import LogLine
from .node import Node

ARKING_ROLES = {"DROPBOX", "EMIX", "DROPBOX_LF"}


class Server(Node):
    """Represents a PRISM server acting in a role, and tracks information about ARK propagation."""

    def __init__(self, name: str, epoch: str):
        super().__init__(name, epoch)

        self.role = "unknown"
        self.arking = False
        self.mpc_ready = False
        self.dropbox_index = None
        self.highest_known_servers = 0
        self.known_servers = []
        self.online = True
        self.tags = {}
        self.event = ""
        self.parent = ""  # for OBDBX servers
        self.peers = []  # for DROPBOX_LF servers
        self.party_id = None
        self.dropbox_stored_count = 0
        self.lsp_table_size = 0
        self.flood_db_size = 0
        self.preproduct_count = 0
        self.active_polls = 0
        self.ongoing_floods = 0
        self.queued_floods = 0
        self.triggered_floods = 0

    def arking_role(self) -> bool:
        return self.role in ARKING_ROLES and (self.party_id is None or self.party_id == 0)

    def stable(self, arking_server_count: int) -> bool:
        return self.online and len(self.known_servers) == arking_server_count

    def historically_stable(self, arking_server_count: int) -> bool:
        return self.highest_known_servers == arking_server_count

    def parse(self, line: LogLine) -> bool:
        if super().parse(line):
            return True

        if line.file_type == "monitor":
            self.parse_prism_server_monitor(line)
            return True
        elif line.file_type == "testapp":
            return True
        else:
            raise ValueError(f"Unknown log file type: {line.file_type}")

    def parse_prism_server_monitor(self, line: LogLine):
        simple_params = [
            "arking",
            "mpc_ready",
            "role",
            "party_id",
            "dropbox_index",
            "dropbox_stored_count",
            "active_polls",
            "lsp_table_size",
            "flood_db_size",
            "preproduct_count",
            "ongoing_floods",
            "queued_floods",
            "triggered_floods",
        ]

        if "epoch" in line.values and line.values["epoch"] != self.epoch:
            return

        for param in simple_params:
            if param in line.values:
                self.__setattr__(param, line.values[param])

        if "valid_ark_count" in line.values:
            self.highest_known_servers = max(line.values["valid_ark_count"], self.highest_known_servers)
        if "known_servers" in line.values:
            self.known_servers = line.values["known_servers"]
            self.highest_known_servers = max(self.highest_known_servers, len(self.known_servers))
        if "monitor_ts" in line.values:
            self.last_activity = datetime.fromisoformat(line.values["monitor_ts"])
            self.first_activity = min(self.first_activity, self.last_activity)
        if "monitor_interval" in line.values:
            self.monitor_interval = line.values["monitor_interval"]

    def is_dropbox(self):
        if self.party_id:
            return False
        return "DROPBOX" in self.role
