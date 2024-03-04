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
from dataclasses import dataclass, asdict
import datetime as dt
import math
from opensearch_dsl import Q
import pandas as pd
import trio
from typing import *

from .query_task import PeriodicESQuery
from .trace_id_query import TracedRequest, filter_tr_factory

EXPIRATION_SECS = 600  # clients try to bootstrap again after 10 minutes


@dataclass(frozen=False)
class BootstrapRequest:
    traced_req: TracedRequest
    epoch: str
    client: str
    received: bool = False
    end_time_ms: int = 0
    in_transit_latency: float = 0.0

    def __str__(self):
        return f"Bootstrap Request for {self.client} (epoch={self.epoch}); " + \
               f"current latency = {self.in_transit_latency:.2f}s" + \
               (" (active)" if self.traced_req.latency else "")


def filter_br_factory(kv_pairs):
    return {k: v for k, v in kv_pairs if k not in ['traced_req', 'end_time_ms']}


class BootstrapQuery(PeriodicESQuery):

    def __init__(self, trigger_send: trio.MemorySendChannel, jaeger: str, update: trio.MemoryReceiveChannel, *args):
        super().__init__(Q("match", operationName="bootstrap-request-ibe-key"), *args)
        self.trigger_send_ch = trigger_send
        self.jaeger = jaeger
        self.issued = {}  # type: Dict[str, TracedRequest]
        # Dict[str, Dict[str, BootstrapRequest]]]  # epoch -> client -> trace_id -> BR
        self.active_bootstraps = {}  # type: Dict[str, BootstrapRequest]
        self.update_recv = update
        self.updated = False  # object-level indicator as 2 places can update data: process_search_results() and
                              # process_active_reqs()

    def __str__(self):
        data_dict = self.get_data()
        if len(data_dict) == 0:
            return f"{__name__}: <No bootstrap messages>\n"
        df = pd.DataFrame(data_dict.values()).set_index("trace_id")
        df.sort_values(by=['client', 'start_time_ms'], inplace=True)
        return f"Bootstrap Requests ({len(data_dict)}):\n" + \
            f"{df.loc[:, ['epoch', 'client', 'latency', 'received']].head(10)}\n"

    def get_data(self, **kwargs):
        return {trace_id: {**asdict(pr, dict_factory=filter_br_factory),
                           **asdict(pr.traced_req, dict_factory=filter_tr_factory)}
                for trace_id, pr in self.active_bootstraps.items()}

    def process_search_results(self, search_results: List) -> bool:
        updated = False
        for result in search_results:
            index = result['traceID']
            issued_req = self.issued.get(index, None)
            if issued_req is None:
                # new bootstrap request
                updated = True
                name = [tag["value"] for tag in result['process']['tags'] if tag["key"] == "hostname"][0]
                epoch = [t["value"] for t in result["tags"] if t["key"] == "epoch"][0]
                start_time_ms = int(result['startTimeMillis'])
                tr = TracedRequest(index,
                                   result['spanID'],
                                   start_time_ms,
                                   dt.datetime.utcfromtimestamp(start_time_ms/1000 + EXPIRATION_SECS), )
                breq = BootstrapRequest(tr,
                                        epoch,
                                        name, )
                self.issued[index] = tr
                try:
                    # trigger tracking tasks for each new bootstrap request:
                    self.trigger_send_ch.send_nowait(breq)
                except trio.WouldBlock:
                    pass  # ignore
        updated |= self.updated  # in case processing active PRs brought a change
        self.updated = False     # reset until checking next time we run process_search_results()
        return updated

    async def process_active_reqs(self):
        async with self.update_recv:
            async for active_req in self.update_recv:
                if isinstance(active_req, BootstrapRequest):
                    if active_req.traced_req.expiration and active_req.traced_req.expiration < dt.datetime.utcnow():
                        self.active_bootstraps.pop(active_req.traced_req.trace_id, None)
                    else:
                        self.active_bootstraps[active_req.traced_req.trace_id] = active_req
                    self.updated = True
                    self.current_update_seqno += 1  # set flag to update UI
