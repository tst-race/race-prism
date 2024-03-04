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
from dataclasses import dataclass, field, asdict
import datetime as dt
import math
from opensearch_dsl import Q
import pandas as pd
import trio
from typing import *

from .QT_network import ClientDBConnection
from .query_task import PeriodicESQuery
from .trace_id_query import TracedRequest, filter_tr_factory


@dataclass(frozen=False)
class PollRequest:
    traced_req: TracedRequest
    epoch: str
    client: str
    poll_route: List[str]
    dropbox: str
    steps: List[Tuple[int, str]] = field(default_factory=list)
    n_steps: int = field(default=0)
    end_time_ms: int = field(default=0)
    in_transit_latency: float = field(default=0.0)

    def __str__(self):
        return f"Poll Request {self.client} -> {self.dropbox} (epoch={self.epoch}); " + \
            f"current latency = {self.in_transit_latency:.2f}s" + \
            (" (active)" if self.traced_req.latency else "") + \
            (" (expired)" if self.traced_req.expiration < dt.datetime.utcnow() else "")


def filter_pr_factory(kv_pairs):
    return {k: v for k, v in kv_pairs if k not in ['traced_req', 'steps', 'poll_route', 'end_time_ms']}


class PollRequestsQuery(PeriodicESQuery):

    def __init__(self, trigger_send: trio.MemorySendChannel,
                 net_update_send: trio.MemorySendChannel,
                 update: trio.MemoryReceiveChannel,
                 jaeger: str,
                 *args):
        super().__init__(Q("match", operationName="poll-request") |
                         Q("match", operationName="poll-start") |
                         Q("match", operationName="poll-stop"),
                         *args)
        self.trigger_send_ch = trigger_send
        self.net_update_send = net_update_send
        self.jaeger = jaeger
        self.issued = {}  # type: Dict[str, TracedRequest]
        self.active_poll_requests = {}  # type: Dict[str, PollRequest]
        self.update_recv = update
        self.updated = False  # object-level indicator as 2 places can update data: process_search_results() and

    def __str__(self):
        data_dict = self.get_data()
        if len(data_dict) == 0:
            return f"{__name__}: <No poll requests yet>\n"
        df = pd.DataFrame(data_dict.values()).set_index("trace_id")
        df.sort_values(by=['client', 'start_time_ms'], inplace=True)
        return f"Active Poll Requests ({len(data_dict)}):\n" + \
            f"{df.loc[:, ['epoch', 'client', 'dropbox', 'latency']].head(10)}\n"

    def get_data(self, **kwargs):
        return {trace_id: {**asdict(pr, dict_factory=filter_pr_factory),
                           **asdict(pr.traced_req, dict_factory=filter_tr_factory)}
                for trace_id, pr in self.active_poll_requests.items()}

    def process_search_results(self, search_results: List) -> bool:
        updated = False
        for result in search_results:
            index = result['traceID']
            if result['operationName'] == "poll-request":
                issued_pr = self.issued.get(index, None)
                if issued_pr is None:
                    # new poll request
                    updated = True
                    name = [tag["value"] for tag in result['process']['tags'] if tag["key"] == "hostname"][0]
                    epoch = [t["value"] for t in result["tags"] if t["key"] == "epoch"][0]
                    poll_route = []
                    expiration = None
                    for log_result in result['logs']:
                        for fields_dict in log_result['fields']:
                            value = fields_dict.get('value', '')
                            if str(value).startswith("Poll route: r"):
                                poll_route = str(value)[12:].split(" -> ")
                            if str(value).startswith("Polling ("):
                                for exp_candidate in str(value).split(", "):
                                    if exp_candidate.startswith("expiration: "):
                                        date_str = exp_candidate[12:].split(")")[0]
                                        expiration = dt.datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S.%f')
                    tr = TracedRequest(index,
                                       result['spanID'],
                                       int(result['startTimeMillis']),
                                       expiration, )
                    self.issued[index] = tr
                    pr = PollRequest(tr,
                                     epoch,
                                     name,
                                     poll_route,
                                     poll_route[-1] if len(poll_route) else None, )
                    if pr.dropbox and expiration and expiration > dt.datetime.utcnow():
                        self.active_poll_requests[pr.traced_req.trace_id] = pr
                        # create directional link client --> dropbox in network
                        if self.net_update_send:
                            try:
                                self.net_update_send.send_nowait(
                                    ClientDBConnection(name, pr.dropbox, pr.epoch, pr.traced_req.start_time_ms))
                            except trio.WouldBlock:
                                pass  # ignore
                        if self.trigger_send_ch:
                            try:
                                # trigger tracking tasks for each new PR:
                                self.trigger_send_ch.send_nowait(pr)
                            except trio.WouldBlock:
                                pass  # ignore
            active_pr = self.active_poll_requests.get(index, None)
            if result['operationName'] == "poll-start":
                if active_pr is not None:
                    # update active poll request
                    updated = True
                    active_pr.n_steps = len(active_pr.poll_route)
                    active_pr.end_time_ms = int(result['startTimeMillis'])
                    active_pr.in_transit_latency = active_pr.traced_req.latency = float(
                        active_pr.end_time_ms - active_pr.traced_req.start_time_ms) / 1000
            if result['operationName'] == "poll-stop":
                if active_pr is not None:
                    updated = True
                    self.active_poll_requests.pop(active_pr.traced_req.trace_id, None)
        updated |= self.updated  # in case processing active PRs brought a change
        self.updated = False     # reset until checking next time we run process_search_results()
        return updated

    async def process_active_prs(self):
        async with self.update_recv:
            async for active_pr in self.update_recv:
                if isinstance(active_pr, PollRequest):
                    if active_pr.traced_req.expiration and active_pr.traced_req.expiration < dt.datetime.utcnow():
                        self.active_poll_requests.pop(active_pr.traced_req.trace_id, None)
                        self.updated = True
                    else:
                        self.active_poll_requests[active_pr.traced_req.trace_id] = active_pr
                        self.updated = True
                    self.current_update_seqno += 1  # set flag to update UI
