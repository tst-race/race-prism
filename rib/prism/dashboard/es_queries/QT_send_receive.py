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
import datetime as dt
from dataclasses import asdict, dataclass, field
import math
import numpy as np
from opensearch_dsl import Q
import pandas as pd
import structlog
import trio
from typing import *

from .events import ReceiveEvent
from .query_task import PeriodicESQuery
from ..gui.dash_st import SendReceiveStats


@dataclass(frozen=False)
class SendStoreReceive:
    traceID: str
    startTimeMillis: int = field(repr=False)
    startTime: dt.datetime = field(repr=False)
    sender: str
    epoch: str
    cleartext: str
    latency: float = math.nan
    storedLatency: float = field(repr=False, default=0.0)
    endTimeMillis: int = field(repr=False, default=None)
    receiver: str = field(repr=False, default=None)
    text: str = field(repr=False, default=None)


class SendReceiveQuery(PeriodicESQuery):

    def __init__(self, jaeger: str, *args, **kwargs):
        super().__init__(Q("match", operationName="receive-message")
                         | Q("match", operationName="send-message")
                         | Q("match", operationName="store-message"),
                         *args)
        self.trigger_send_ch = None
        self.jaeger = jaeger
        self.matched = {}  # type: Dict[str, SendStoreReceive]
        self.latencies = None  # type: Optional[pd.DataFrame]
        self.statistics = None  # type: Optional[SendReceiveStats]
        self.epoch = kwargs["epoch"]
        self._logger = structlog.get_logger("prism")

    def __str__(self):
        stats = self.get_data(epoch=self.epoch)
        if len(stats) == 0:
            return f"{__name__}: <No messages yet (for epoch = {self.epoch})>\n"

        msgs_epoch = f"\nNo Transmissions in epoch = {self.epoch}\n"
        ts_epoch = stats.pop("ts", None)
        if ts_epoch:
            pd_latencies = pd.DataFrame.from_dict(ts_epoch, "index")
            if len(pd_latencies):
                delivered_ = pd_latencies['latency'] > 0
                missing_ = (pd_latencies['latency'] == 0) & (pd_latencies['storedLatency'] == 0)
                stored_ = (pd_latencies['latency'] == 0) & (pd_latencies['storedLatency'] > 0)
                msgs_epoch = f"\n{len(pd_latencies[delivered_])} RECEIVED + {len(pd_latencies[stored_])} STORED + " + \
                             f"{len(pd_latencies[missing_])} MISSING = {len(ts_epoch)} SENT in epoch = {self.epoch}\n"

        return str(SendReceiveStats(**stats)) + msgs_epoch

    def get_data(self, **kwargs):
        if self.latencies is None or len(self.latencies['latency']) == 0 or self.statistics is None:
            return {}
        filtered_epoch = kwargs.get('epoch', self.epoch)

        ts_df = self.latencies[self.latencies['epoch'] == filtered_epoch] \
                    .loc[:, ['startTimeMillis', 'latency', 'storedLatency', 'cleartext']].fillna(value=0)

        return asdict(self.statistics) | {'ts': ts_df.to_dict('index')}

    def process_search_results(self, search_results: List) -> bool:
        updated_indices = set()
        for result in search_results:
            index = result['traceID']
            match = self.matched.get(index)
            # update match result, if "new" receive-message
            if match:
                if result['operationName'] == "receive-message":
                    if not match.receiver:
                        match.endTimeMillis = int(result['startTimeMillis'])
                        match.latency = (match.endTimeMillis - match.startTimeMillis) / 1000.0
                        match.epoch = [t["value"] for t in result["tags"] if t["key"] == "epoch"][0]
                        match.receiver = result['process']['serviceName'][6:]
                        match.text = f"{match.sender} -> {match.receiver} took {match.latency:.2f}s"
                        updated_indices.add(index)
                        if self.trigger_send_ch:
                            try:
                                self.trigger_send_ch.send_nowait(
                                    ReceiveEvent(
                                        result['traceID'],
                                        result['spanID'],
                                        endTimeMillis=int(result['startTimeMillis']),
                                        # + int(result['duration'])*1000,
                                        endTime=dt.datetime.fromtimestamp((int(result['startTimeMillis']) / 1000)),
                                        # (int(result['startTimeMillis']) + int(result['duration'])*1000)/1000),
                                        messageSize=0))  # NOTE: PRISM is currently not tagging message information
                            except trio.WouldBlock:
                                pass  # ignore
                elif result['operationName'] == "store-message":
                    # add the first store event to matched
                    if match.storedLatency == 0:
                        match.storedLatency = (int(result['startTimeMillis']) - match.startTimeMillis) / 1000.0
                        match.epoch = [t["value"] for t in result["tags"] if t["key"] == "epoch"][0]
                        updated_indices.add(index)
            else:
                if result['operationName'] == "send-message":
                    str_tags = {t["key"]: t["value"] for t in result["tags"] if t["type"] == "string"}
                    ssr = SendStoreReceive(
                        index,
                        int(result['startTimeMillis']),
                        dt.datetime.fromtimestamp(round(int(result['startTimeMillis']) / 1000)),
                        result['process']['serviceName'][6:],
                        str_tags["epoch"],
                        str_tags["message"],
                    )
                    # filter out messages from or to CLIENT REGISTRATION committee:
                    if str_tags["sender"].startswith("prism_client_registration") or \
                            str_tags["recipient"].startswith("prism_client_registration"):
                        self._logger.warning(f"Not tracing {ssr} because it entail CLIENT REGISTRATION")
                    else:
                        self.matched[index] = ssr
                        updated_indices.add(index)
        if len(updated_indices):
            new_latencies = pd.DataFrame([self.matched[k] for k in updated_indices]).set_index('traceID')
            if self.latencies is None:
                self.latencies = new_latencies
            else:
                # from: https://stackoverflow.com/a/33002097/3816489
                df = pd.concat([self.latencies[~self.latencies.index.isin(new_latencies.index)], new_latencies])
                df.update(new_latencies)
                self.latencies = df
            # calculate new metrics from latencies:
            n_matched = len(self.latencies[self.latencies['latency'] > 0])
            avg_latency = self.latencies['latency'].mean() if n_matched else 0.0
            xs = list(range(5, 101, 5))
            q_latencies = self.latencies['latency'].quantile(q=[x/100 for x in xs]).tolist() if n_matched else [],
            ys = q_latencies[0] if len(q_latencies) else []
            self.statistics = SendReceiveStats(
                len(self.latencies),
                self.statistics.n_sent if self.statistics else 0,
                n_matched,
                self.statistics.n_matched if self.statistics else 0,
                avg_latency,
                self.latencies['latency'].quantile(0.5) if n_matched else 0.0,
                self.latencies['latency'].quantile(0.9) if n_matched else 0.0,
                int(np.argmin([np.absolute(yl - avg_latency) for yl in ys])) if len(ys) else 0,
                xs,
                ys,
            )

            return True
        return False
