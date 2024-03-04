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
from dataclasses import asdict, dataclass, field
import datetime as dt
import math
from natsort import natsorted
import networkx as nx
from opensearch_dsl import Q
from operator import attrgetter
import pandas as pd
import random
from statistics import mean
import structlog
from timeit import default_timer as timer
import trio
from typing import *
import yaml

from .query_task import PeriodicESQuery
from ..gui.dash_st import Node, Edge, NetworkStats


def get_connections(source: str, sinks: List[str], link_type: str) -> Set[Tuple[str, str]]:
    connections = set()
    if link_type.endswith("BIDI") or link_type.endswith("SEND"):
        connections.update([(source, sink) for sink in sinks])
    if link_type.endswith("BIDI") or link_type.endswith("RECV"):
        connections.update([(sink, source) for sink in sinks])
    return connections


def shorthand(name: str) -> str:
    return name[5] + str(int(name[-5:]))  # remove LEADING zeros!


def longhand(sh: str) -> str:
    return ("race-client-" if sh[0] == "c" else "race-server-") + f"{int(sh[1:]):05d}"


def format_delta(delta: dt.timedelta) -> str:
    # break up into days, hours, etc.
    hours, rem = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return f'{(hours + 24*delta.days):02d}:{minutes:02d}:{seconds:02d}'


@dataclass(frozen=False)
class ClientDBConnection:
    client: str = field(repr=False)
    client_shorthand: str = field(init=False)
    dropbox: str = field(repr=False)
    db_shorthand: str = field(init=False)
    epoch: str
    start_time_ms: int

    def __post_init__(self):
        self.client_shorthand = shorthand(self.client)
        self.db_shorthand = shorthand(self.dropbox)


@dataclass(frozen=False)
class AliveEvent:
    name: str = field(repr=False)
    shorthand: str = field(init=False)
    operation: str
    epoch: str
    last_seen_ms: int
    missing: bool = False

    def __post_init__(self):
        self.shorthand = shorthand(self.name)


@dataclass(frozen=True)
class LastSeenEvent:
    operation: str
    shorthand: str
    service: str
    earliest: int
    epoch: str = None


@dataclass(frozen=False)
class NetworkStatus:
    n_valid_servers: int  # n(EMIX) + n(DROPBOX committees)
    role_distribution: Dict[str, List[str]]
    client_out_degs: Dict[int, List[str]]
    server_out_degs: Dict[int, List[str]]
    server_avg_degree: float
    server_max_degree: int
    server_diameter: int
    servers: List[Node]
    edges: List[Edge]
    missing: List[Tuple[str, int]]
    comms: str


class NetworkQuery(PeriodicESQuery):

    def __init__(self, alive_recv: trio.MemoryReceiveChannel, *args, **kwargs):
        super().__init__(#Q("match", operationName="connection-open")
                         #| Q("match", operationName="connection-closed") |
                         Q("match", operationName="CONNECTION_OPEN")
                         # | Q("match", operationName="CONNECTION_CLOSED")
                         | Q("match", operationName="neighbor-connected")
                         | Q("match", operationName="neighbor-disconnected")
                         | Q("match", operationName="role-choice")
                         | Q("match", operationName="client-started"),
                         *args)
        self.net_updates_recv = alive_recv
        self.epoch = kwargs["epoch"]
        self.verbose = kwargs.get("verbose", False)
        self.clients = {}  # type: Dict[str, Node]  # shorthand -> client
        self.registration = {}  # type: Dict[str, Node]  # shorthand -> bootstrap node
        self.servers_by_epoch = {}  # type: Dict[str, Dict[str, Node]]  #  epoch -> shorthand -> server
        self.last_epoch_by_server = {}  # type: Dict[str, str]  # shorthand -> last epoch seen
        self.edges_by_epoch = {}  # type: Dict[str, Dict[Tuple[str, str], Edge]]  # epoch -> (src, dst) -> edge
        self.alives_by_epoch = {}  # type: Dict[str, Dict[Tuple[str, str], AliveEvent]]  # epoch -> (shorthand, op) -> alive node stats
        self.comms_by_epoch = {}  # type: Dict[str, Dict[str, Set[str]]]  # epoch -> Comms channels seen -> persona types
        self.up_since = math.inf
        self.network_stats_by_epoch = {}  # type: Dict[str, NetworkStatus]  # epoch -> detailed stats for network
        self.last_seen_send, self.last_seen_recv = trio.open_memory_channel(math.inf)
        self._logger = structlog.get_logger("prism")

    async def start_soon(self, nursery: trio.Nursery):
        nursery.start_soon(super().start_soon, nursery)
        nursery.start_soon(self.process_alives)
        nursery.start_soon(self.find_last_seen)

    def __str__(self):
        stats = self.get_data(show_graph=self.verbose)
        if len(stats) == 0:
            return ""
        current_stats = NetworkStats(**stats)

        known_str = f"{current_stats.n_clients} clients " + \
                    (f"x {current_stats.n_registration} registration committee " if current_stats.n_registration
                     else "") + \
                    f"x {current_stats.n_servers} servers (for epoch = {self.epoch})\n"

        up_str = ""
        if self.up_since < math.inf:
            comms_str = "\n"
            if current_stats.comms:
                comms_str = f"{current_stats.comms}\n\n"
            up_since = dt.datetime.fromtimestamp(self.up_since)
            up_str = f"Up since: {up_since.strftime('%H:%M:%S on %Y-%m-%d')}\n" + \
                     f"Up time:  {format_delta(dt.datetime.now() - up_since)}\n{comms_str}"

        missing_str = ""
        if current_stats.missing:
            missing_str = f"{len(current_stats.missing)} missing nodes (for epoch = {self.epoch}):\n  " \
                          + ", ".join(f"{sh} -> last seen " +
                                      f"{dt.datetime.fromtimestamp(last_seen / 1000).strftime('%m-%d %H:%M:%S')}"
                                      for sh, last_seen in natsorted(current_stats.missing[:5])) + "\n\n"

        nodes_str = ""
        if len(current_stats.servers) > 0:
            max_length = 10
            nodes = pd.DataFrame(natsorted(current_stats.servers))
            nodes_str = \
                f"\n\n{len(nodes)} Nodes{'' if len(nodes) < max_length else f' (last {max_length})'}:" + \
                f"\n{nodes.loc[:, ['shorthand', 'role', 'dropbox_index', 'party_id', 'peers']].tail(max_length)}" + \
                f"\n(etc.)"
        return f"{known_str}{up_str}{missing_str}{str(current_stats)}{nodes_str}\n"

    def get_data(self, **kwargs):
        filtered_epoch = kwargs.get('epoch', self.epoch)
        show_graph = kwargs.get('show_graph', False)

        current_stats = self.network_stats_by_epoch.get(filtered_epoch, None)
        return asdict(NetworkStats(
            self.up_since if self.up_since < math.inf else 0,
            len(self.clients),
            len(self.registration),
            len(current_stats.servers) if current_stats else 0,
            current_stats.n_valid_servers if current_stats else -1,
            {role: len(l) for role, l in current_stats.role_distribution.items()} if current_stats else {},
            {str(deg): len(l) for deg, l in current_stats.client_out_degs.items()} if current_stats else {},
            {str(deg): len(l) for deg, l in current_stats.server_out_degs.items()} if current_stats else {},
            current_stats.server_avg_degree if current_stats else 0,
            current_stats.server_max_degree if current_stats else 0,
            current_stats.server_diameter if current_stats else -1,
            missing=current_stats.missing if current_stats else [],
            clients=[asdict(v) for v in self.clients.values()] if show_graph else [],
            reg_nodes=[asdict(v) for v in self.registration.values()] if show_graph else [],
            servers=[asdict(v) for v in current_stats.servers] if show_graph and current_stats else [],
            edges=[asdict(e) for e in current_stats.edges] if show_graph and current_stats else [],
            comms=current_stats.comms if current_stats else "",
        ))

    def _update_stats_for(self, epoch: str) -> NetworkStatus:
        n_valid_servers = 0
        role_distribution = {}  # type: Dict[str, List[str]]
        servers = natsorted(self.servers_by_epoch.get(epoch, {}).values(), key=attrgetter("shorthand"))
        for server in servers:
            current_roles = role_distribution.get(server.role, [])
            current_roles.append(server.shorthand)
            role_distribution[server.role] = current_roles
            if server.role == "EMIX" or server.party_id == 0:
                n_valid_servers += 1

        graph = nx.DiGraph()
        deg_by_client = {}  # type: Dict[str, int]
        edges = list(self.edges_by_epoch.get(epoch, {}).values())
        for e in edges:
            # only track DIRECT = server links
            if not e.connectionType.endswith('INDIRECT'):
                graph.add_edge(e.src, e.dst, )  # conn_id=e.connectionId) add attributes?
            if e.src.startswith("c"):
                current_deg = deg_by_client.get(e.src, 0)
                deg_by_client[e.src] = current_deg + 1
        # calculate server out-degrees:
        deg_by_server = {s: deg for s, deg in graph.out_degree()}  # type: Dict[str, int]
        server_out_degs = {}  # type: Dict[int, List[str]]
        for s, deg in deg_by_server.items():
            current_servers = server_out_degs.get(deg, [])
            current_servers.append(s)
            server_out_degs[deg] = natsorted(current_servers)

        # calculate client out-degrees:
        client_out_degs = {}  # type: Dict[int, List[str]]
        for c, deg in deg_by_client.items():
            current_clients = client_out_degs.get(deg, [])
            current_clients.append(c)
            client_out_degs[deg] = natsorted(current_clients)

        missing_shorthands = {n.shorthand: n.last_seen_ms for n in self.alives_by_epoch.get(epoch, {}).values()
                              if n.missing}

        comms = self.comms_by_epoch.get(epoch, {})
        comms_keys = sorted(comms.keys())
        comms_list = [(f"{comms_key}", f" ({'|'.join(sorted(comms[comms_key]))})" if len(comms[comms_key]) else "")
                     for comms_key in comms_keys]
        comms_str = f"Comms: {', '.join([''.join(comms_tuple) for comms_tuple in comms_list])}"

        return NetworkStatus(
            n_valid_servers,
            role_distribution,
            {key: client_out_degs[key] for key in sorted(client_out_degs.keys())},
            {key: server_out_degs[key] for key in sorted(server_out_degs.keys())},
            mean(list(deg_by_server.values())) if len(deg_by_server) else 0.0,
            max(list(deg_by_server.values())) if len(deg_by_server) else 0.0,
            nx.algorithms.diameter(graph) if len(graph) and nx.algorithms.is_strongly_connected(graph) else 0,
            servers,
            edges,
            [(k, v) for k, v in missing_shorthands.items()],
            comms_str,
        )

    def process_search_results(self, search_results: List) -> bool:
        tic = timer()
        updated = False
        updated_epochs = set()
        for result in search_results:
            if int(result['startTimeMillis']) / 1000.0 < self.up_since:
                self.up_since = int(result['startTimeMillis']) / 1000.0
                updated = True
            sh = shorthand([tag["value"] for tag in result['process']['tags'] if tag["key"] == "hostname"][0])
            if result['operationName'] == "role-choice":
                str_tags = {t["key"]: t["value"] for t in result["tags"] if t["key"] in ["role",
                                                                                         "dropbox_index",
                                                                                         "party_id",
                                                                                         "peer_status",
                                                                                         "pseudonym",
                                                                                         "epoch"]
                            if t["value"] != "None"}
                if str_tags["role"] == "CLIENT_REGISTRATION":
                    self._init_alive_event(sh, result["startTimeMillis"], "alive-loop", str_tags["epoch"])
                    continue  # this server will also emit "client-started" and we track it there
                if "peer_status" in str_tags:
                    peer_status = yaml.safe_load(str_tags["peer_status"])
                    peers = [shorthand(p["name"]) for p in peer_status]
                else:
                    peers = []
                server = Node(sh,
                              str_tags["pseudonym"],
                              result["startTimeMillis"],
                              str_tags["role"],
                              int(str_tags.get("dropbox_index", -1)),
                              int(str_tags.get("party_id", -1)),
                              peers,)
                servers = self.servers_by_epoch.get(str_tags["epoch"], {})
                if server.shorthand not in servers:
                    updated_epochs.add(str_tags["epoch"])
                    servers[server.shorthand] = server
                    self.servers_by_epoch[str_tags["epoch"]] = servers
                    self.last_epoch_by_server[server.shorthand] = str_tags["epoch"]
                    # search for last alive-loop with >result["startTimeMillis"] and epoch=str_tags["epoch"]:
                    self._init_alive_event(sh, server.startTimeMillis, "alive-loop", str_tags["epoch"])
            elif result['operationName'] == "client-started":
                # currently, CLIENT_REGISTRATION nodes are deployed as race-server-NNNNN, so their shorthand starts with
                # an 's' but they do emit "client-started"
                if sh[0] == "c":
                    if sh not in self.clients:
                        self.clients[sh] = Node(sh, "", result["startTimeMillis"])
                else:
                    if sh not in self.registration:
                        self.registration[sh] = Node(sh, "", result["startTimeMillis"])
                # search for last monitor-client with >result["startTimeMillis"]:
                self._init_alive_event(sh, result["startTimeMillis"], "monitor-client")
                updated = True
            elif result['operationName'].startswith("CONNECTION"):
                str_tags = {t["key"]: t["value"] for t in result["tags"] if t["type"] == "string"}
                if "linkType" not in str_tags:
                    continue
                personas = str_tags.get("personas", "").split(", ")
                # record Comms seen:
                unified_epoch = str_tags.get("epoch", "genesis")
                unified_link_id = str_tags.get("link_id", str_tags.get("linkId", "//"))
                comms_name = unified_link_id.split('/')[1]
                current_comms = self.comms_by_epoch.get(unified_epoch, {})
                current_comms_types = current_comms.get(comms_name, set())
                current_comms_types.update({p_name.split('-')[0] if p_name.startswith("epoch-") else p_name for p_name
                                           in personas if p_name.startswith("*") or p_name.startswith("epoch-")})
                current_comms[comms_name] = current_comms_types
                self.comms_by_epoch[unified_epoch] = current_comms
                # for conn in get_connections(sh,
                #                             [shorthand(p) for p in personas if p.startswith("race-")],
                #                             str_tags["linkType"]):
                #     if not conn[0][0] == 'c' and not conn[1][0] == 'c':
                #         # don't trace server-to-server connections here anymore; TODO: also exempt CLIENT REG?
                #         # TODO: once we have other means of tracing client/client reg. connections,
                #         #  drop CONNECTION_CLOSED and only use CONNECTION_OPEN to collect link IDs.
                #         continue
                #     edge = Edge(conn[0], conn[1],
                #                 unified_epoch,
                #                 str_tags["connectionType"],
                #                 result["startTimeMillis"],
                #                 str_tags["linkType"],
                #                 unified_link_id,
                #                 str_tags.get("personas", ""), )
                #     if result['operationName'].lower().endswith("open"):
                #         if conn[0] == conn[1]:
                #             self._logger.warning(f"Trying to OPEN a connection to myself ({conn[0]})")
                #         else:
                #             edges = self.edges_by_epoch.get(edge.epoch, {})
                #             if conn not in edges:
                #                 edges[conn] = edge
                #                 self.edges_by_epoch[edge.epoch] = edges
                #                 updated_epochs.add(edge.epoch)
                #     if result['operationName'].lower().endswith("closed"):
                #         edges = self.edges_by_epoch.get(edge.epoch, {})
                #         popped_edge = edges.pop(conn, None)
                #         self.edges_by_epoch[edge.epoch] = edges
                #         if popped_edge:
                #             updated_epochs.add(edge.epoch)
            elif result['operationName'].startswith("neighbor-"):
                str_tags = {t["key"]: t["value"] for t in result["tags"] if t["type"] == "string"}
                conn = (sh, shorthand(str_tags["persona"]))
                edge = Edge(conn[0], conn[1],
                            str_tags.get("epoch", "genesis"),
                            "NEIGHBOR_DIRECT",
                            result["startTimeMillis"], )
                if result['operationName'] == "neighbor-connected":
                    edges = self.edges_by_epoch.get(edge.epoch, {})
                    if conn not in edges:
                        edges[conn] = edge
                        self.edges_by_epoch[edge.epoch] = edges
                        updated_epochs.add(edge.epoch)
                if result['operationName'] == "neighbor-disconnected":
                    edges = self.edges_by_epoch.get(edge.epoch, {})
                    popped_edge = edges.pop(conn, None)
                    self.edges_by_epoch[edge.epoch] = edges
                    if popped_edge:
                        updated_epochs.add(edge.epoch)
        # re-calculate network stats for any changed epochs
        toc = None
        if len(updated_epochs):
            for epoch in updated_epochs:
                self.network_stats_by_epoch[epoch] = self._update_stats_for(epoch)
            toc = timer()
        elif updated:
            # go through all epochs and update network stats
            for epoch in self.network_stats_by_epoch.keys():
                self.network_stats_by_epoch[epoch] = self._update_stats_for(epoch)
            toc = timer()
        if toc:
            self._logger.debug(f"NETWORK: Processing {len(search_results)} search results took {toc - tic:.3f}s")
            return True
        return False

    async def process_alives(self):
        if not self.net_updates_recv:
            return  # nothing left to do
        async with self.net_updates_recv:
            async for updates in self.net_updates_recv:
                updated_epochs = set()
                if isinstance(updates, list):
                    # go through all alive events in this list and update time stamp, missing status = False
                    # for those shorthands missing for the first time or switching back to not missing, signal to UI
                    currently_not_missing_by_epoch = {  # type: Dict[Tuple[str, str], Set[str]]  # epoch -> (sh, op) not missing
                        k: set([shop for shop, ae in v.items() if not ae.missing]) for k, v in self.alives_by_epoch.items()}
                    newly_not_missing_by_epoch = {}  # type: Dict[str, Set[Tuple[str, str]]]  # epoch -> (sh, op) not missing
                    for alive in updates:
                        assert isinstance(alive, AliveEvent)
                        newly_not_missing = newly_not_missing_by_epoch.get(alive.epoch, set())
                        if (alive.shorthand, alive.operation) not in newly_not_missing:
                            updated_epochs.add(alive.epoch)
                        newly_not_missing.add((alive.shorthand, alive.operation))
                        newly_not_missing_by_epoch[alive.epoch] = newly_not_missing
                        if self._update_alive_event(alive.shorthand, alive.epoch, alive.last_seen_ms, alive.operation):
                            updated_epochs.add(alive.epoch)
                    for epoch, newly_not_missing in newly_not_missing_by_epoch.items():
                        newly_missing = currently_not_missing_by_epoch.get(epoch, set()) - newly_not_missing
                        for shop in newly_missing:
                            updated_epochs.add(epoch)
                            self.alives_by_epoch[epoch][shop].missing = True
                elif isinstance(updates, ClientDBConnection):
                    # add new client->dropbox link and update
                    conn = (updates.client_shorthand, updates.db_shorthand)
                    edge = Edge(conn[0], conn[1],
                                updates.epoch,
                                "CLIENT_INDIRECT",
                                updates.start_time_ms, )
                    edges = self.edges_by_epoch.get(edge.epoch, {})
                    if conn not in edges:
                        edges[conn] = edge
                        self.edges_by_epoch[edge.epoch] = edges
                        updated_epochs.add(edge.epoch)
                if len(updated_epochs):
                    for epoch in updated_epochs:
                        self.network_stats_by_epoch[epoch] = self._update_stats_for(epoch)
                    self.current_update_seqno += 1  # set flag to update UI

    async def find_last_seen(self):
        async with self.last_seen_recv:
            async for last_seen in self.last_seen_recv:
                assert isinstance(last_seen, LastSeenEvent)
                await trio.sleep(random.random())
                current_range = {"gt": last_seen.earliest}  # type: Dict[str, int]
                results = self.es_client.execute_search(current_range, self.source_fields,
                                                        Q("match", operationName=last_seen.operation) &
                                                        Q("match", **{"process.serviceName": last_seen.service}),
                                                        last_n=1)
                if len(results) == 1:
                    epoch = [tag["value"] for tag in results[0]['tags'] if tag["key"] == "epoch"][0]
                    alives_map = self.alives_by_epoch.get(epoch, {})
                    alive = alives_map.get((last_seen.shorthand, last_seen.operation), None)
                    if alive and alive.last_seen_ms < results[0]["startTimeMillis"]:
                        alive.last_seen_ms = results[0]["startTimeMillis"]
                        alive.missing = False
                        alives_map[(last_seen.shorthand, last_seen.operation)] = alive
                        self.alives_by_epoch[epoch] = alives_map
                        self.network_stats_by_epoch[epoch] = self._update_stats_for(epoch)
                        self.current_update_seqno += 1  # set flag to update UI

    def _update_alive_event(self, sh: str, epoch: str, start_time_ms: int, operation: str) -> bool:
        # update this alive event and return True if previous missing status was True (i.e., a node came back to life)
        alives_map = self.alives_by_epoch.get(epoch, {})
        new_alive = AliveEvent(longhand(sh), operation, epoch, start_time_ms)
        previous_alive = alives_map.get((sh, operation), new_alive)
        alives_map[(sh, operation)] = new_alive
        self.alives_by_epoch[epoch] = alives_map
        return previous_alive.missing

    def _init_alive_event(self, sh: str, start_time_ms: int, operation: str, epoch: str = None):
        self._update_alive_event(sh, epoch if epoch else "genesis", start_time_ms, operation)
        try:
            self.last_seen_send.send_nowait(
                LastSeenEvent(operation,
                              sh,
                              f"prism:{longhand(sh)}",
                              start_time_ms,
                              epoch))
        except trio.WouldBlock:
            pass  # ignore
