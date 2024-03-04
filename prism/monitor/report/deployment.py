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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import chain
from typing import Dict, List

from prism.monitor.node import Client, Server, MessageChecker, Replay
from prism.monitor.reader import ReaderStats
from .report import Report


@dataclass
class Deployment:
    """Collects all relevant repositories of statistics in one place, and generates reports on the state of the
    system."""

    reader_stats: ReaderStats
    epoch: str
    beginning: datetime = field(default=datetime.max.replace(tzinfo=timezone.utc))
    now: datetime = field(default=datetime.min.replace(tzinfo=timezone.utc))
    replay: Replay = field(default_factory=Replay)
    message_checker: MessageChecker = field(default_factory=MessageChecker)
    clients: Dict[str, Client] = field(default_factory=dict)
    servers: Dict[str, Server] = field(default_factory=dict)
    live_servers: List[Server] = field(default_factory=list)
    dead_servers: List[Server] = field(default_factory=list)
    live_clients: List[Client] = field(default_factory=list)
    dead_clients: List[Client] = field(default_factory=list)

    def add_client(self, name: str):
        self.clients[name] = Client(name, self.epoch, self.message_checker)

    def add_server(self, name: str):
        self.servers[name] = Server(name, self.epoch)

    def generate_report(self, verbose=False) -> Report:
        report = Report()

        last_activities = {
            node.name: node.last_activity for node in chain(self.clients.values(), self.servers.values())
        }
        first_activities = {
            node.name: node.first_activity for node in chain(self.clients.values(), self.servers.values())
        }
        if last_activities:
            self.now = max(last_activities.values())
            self.beginning = min(first_activities.values())
            self.live_clients = [client for client in self.clients.values() if client.alive(self.now)]
            self.dead_clients = sorted([client for client in self.clients.values() if not client.alive(self.now)],
                                       key=lambda c: c.last_activity)
            self.live_servers = [server for server in self.servers.values() if server.alive(self.now)]
            self.dead_servers = sorted([server for server in self.servers.values() if not server.alive(self.now)],
                                       key=lambda s: s.last_activity)

        report.verbose = verbose
        report.deployment_stats = {
            "lines_read": self.reader_stats.lines_read,
            "client_count": len(self.clients),
            "server_count": len(self.servers),
            "beginning": self.beginning,
            "now": self.now,
            "last_activities": last_activities,
            "epoch": self.epoch,
        }
        report.server_stats = self.server_report()
        report.client_stats = self.client_report()
        report.error_stats = {
            "client": [node for node in self.clients.values() if node.errors],
            "server": [node for node in self.servers.values() if node.errors],
        }

        if self.replay:
            report.replay_stats = self.replay.stats([60])

        return report

    def server_report(self):
        ls_db_sizes = [server.lsp_table_size for server in self.live_servers if server.lsp_table_size]
        avg_lsp_table = None
        if ls_db_sizes:
            avg_lsp_table = sum(ls_db_sizes) / len(ls_db_sizes)

        flood_db_sizes = [server.flood_db_size for server in self.live_servers if server.flood_db_size]
        avg_flood_db = None
        if flood_db_sizes:
            avg_flood_db = sum(flood_db_sizes) / len(flood_db_sizes)

        ongoing_floods = sum([server.ongoing_floods for server in self.live_servers])
        if self.live_servers:
            avg_ongoing_floods = ongoing_floods / len(self.live_servers)
        else:
            avg_ongoing_floods = 0

        queued_floods = sum([server.queued_floods for server in self.live_servers])
        if self.live_servers:
            avg_queued_floods = queued_floods / len(self.live_servers)
        else:
            avg_queued_floods = 0

        triggered_floods = sum([server.triggered_floods for server in self.servers.values()])

        stats = {
            "count": len(self.servers),
            "alive": self.live_servers,
            "dead": self.dead_servers,
            "ark": self.server_ark_report(),
            "mpc": self.server_mpc_report(),
            "stored": sum(server.dropbox_stored_count for server in self.live_servers if server.is_dropbox()),
            "polls": sum(server.active_polls for server in self.live_servers if server.is_dropbox()),
            "stored_servers": [server for server in self.live_servers if server.dropbox_stored_count],
            "avg_lsp_table": avg_lsp_table,
            "avg_flood_db": avg_flood_db,
            "avg_ongoing_floods": avg_ongoing_floods,
            "avg_queued_floods": avg_queued_floods,
            "triggered_floods": triggered_floods,
        }
        return stats

    def server_ark_report(self):
        arking_servers = [server for server in self.live_servers if server.arking_role()]
        target_count = len(arking_servers)
        historically_stable = list(filter(lambda s: s.historically_stable(target_count), arking_servers))
        stable_servers = list(filter(lambda s: s.stable(target_count), historically_stable))
        # unstable_servers = list(filter(lambda s: not s.stable(target_count), arking_servers))
        # destabilized = list(filter(lambda s: not s.stable(target_count), historically_stable))

        ark_report = {
            "arking": arking_servers,
            # "historically_stable": historically_stable,
            "stable": stable_servers,
            # "unstable": unstable_servers,
            # "destabilized": destabilized,
        }

        if len(stable_servers) != len(arking_servers):
            avg_count = float(sum([len(server.known_servers) for server in arking_servers])) / len(arking_servers)
            ark_report["average_known"] = avg_count
            # ark_report["missing"] = {
            #     server.name: len([x for x in unstable_servers if server.name not in x.known_servers])
            #     for server in arking_servers
            # }

        return ark_report

    def server_mpc_report(self):
        mpc_servers = [server for server in self.live_servers if server.party_id == 0]
        bootstrapped = [server for server in mpc_servers if server.mpc_ready]

        mpc_report = {"bootstrapped": bootstrapped, "servers": mpc_servers}

        return mpc_report

    def client_report(self):
        polling = 0
        backlog = 0
        valid_count = 0
        expired_count = 0
        expiry_time_total = 0.0

        for client in self.clients.values():
            stats = client.stats
            if not stats or not client.alive(self.now):
                continue
            if stats.polling:
                polling += 1
            backlog += stats.backlog
            valid_count += stats.valid_server_count
            expired_count += stats.expired_server_count
            expiry_time_total += stats.avg_time_to_expiry

        return {
            "messages": self.message_checker.stats(),
            "alive": len(self.live_clients),
            "dead": self.dead_clients,
            "polling": polling,
            "backlog": backlog,
            "avg_valid_servers": valid_count / (len(self.live_clients) or 1),
            "expired_arks": expired_count,
            "average_ttl": expiry_time_total / (len(self.live_clients) or 1),
        }
