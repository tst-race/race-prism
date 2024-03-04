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
from dataclasses import asdict
from opensearch_dsl import Q
from typing import *

from .QT_network import NetworkQuery
from .query_task import PeriodicESQuery
from ..gui.dash_st import DatabaseStats


class DatabasesQuery(PeriodicESQuery):

    def __init__(self, network_task: NetworkQuery, *args, **kwargs):
        super().__init__(
            Q("match", operationName="updated-LS-table")
            | Q("match", operationName="valid-servers")
            | Q("match", operationName="flood-stored")
            , *args)
        self.network_task = network_task
        self.LSP_sizes = {}  # type: Dict[Tuple[str, str], int]  # (epoch, server name) => size of LSP table
        self.flood_sizes = {}  # type: Dict[Tuple[str, str], int]  # (epoch, server name) => size of flooding DB
        self.valid_servers = {}  # type: Dict[Tuple[str, str], int]  # (epoch, client name) => size of valid servers
        self.epoch = kwargs["epoch"]

    def __str__(self):
        stats = self.get_data(epoch=self.epoch)
        if len(stats) == 0:
            return f"{__name__}: <No database sizes yet for epoch = {self.epoch}>\n"
        return str(DatabaseStats(**stats))

    def get_data(self, **kwargs):
        filtered_epoch = kwargs.get('epoch', self.epoch)

        # calculate number of current LSP roles for this epoch
        n_lsp_servers = 0
        n_valid_servers = -1
        if self.network_task:
            net_data = self.network_task.get_data(epoch=filtered_epoch)
            n_lsp_servers = net_data.get('n_servers', n_lsp_servers)
            n_valid_servers = net_data.get('n_valid_servers', n_valid_servers)

        return asdict(DatabaseStats(
            n_lsp_servers,
            n_valid_servers,
            lsp_sizes=[size for (epoch, _), size in self.LSP_sizes.items() if epoch == filtered_epoch],
            flood_sizes=[size for (epoch, _), size in self.flood_sizes.items() if epoch == filtered_epoch],
            valid_sizes=[size for (epoch, _), size in self.valid_servers.items() if epoch == filtered_epoch],
        ))

    def process_search_results(self, search_results: List) -> bool:
        updated = False
        for result in search_results:
            name = [tag["value"] for tag in result['process']['tags'] if tag["key"] == "hostname"][0]
            str_tags = {t["key"]: t["value"] for t in result["tags"]
                        if t["key"] in ["epoch",
                                        "lsp_table_size",
                                        "db_size",
                                        "count", ]}
            key = str_tags["epoch"], name
            if result['operationName'] == "updated-LS-table":
                previous = self.LSP_sizes.get(key, -1)
                updated = previous != int(str_tags["lsp_table_size"])
                self.LSP_sizes[key] = int(str_tags["lsp_table_size"])
            elif result['operationName'] == "flood-stored":
                previous = self.flood_sizes.get(key, -1)
                updated = previous != int(str_tags["db_size"])
                self.flood_sizes[key] = int(str_tags["db_size"])
            elif result['operationName'] == "valid-servers":
                previous = self.valid_servers.get(key, -1)
                updated = previous != int(str_tags["count"])
                self.valid_servers[key] = int(str_tags["count"])
        return updated
