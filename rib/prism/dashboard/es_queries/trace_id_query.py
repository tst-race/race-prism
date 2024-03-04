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
from abc import abstractmethod
from dataclasses import dataclass
import datetime as dt
import math
from opensearch_dsl import Q
import random
import trio
from typing import *

from .es_client import ESClientTrioAware


@dataclass(frozen=False)
class TracedRequest:
    trace_id: str
    span_id: str
    start_time_ms: int
    expiration: dt.datetime = None
    latency: float = 0.0  # setting this to something other than 0 will end this task


class TracingIdTask:

    def __init__(self, es_client: ESClientTrioAware, start_time: int,
                 traced_req: TracedRequest, update_send: trio.MemorySendChannel,
                 max_sleep_secs: int = 15, op_name: str = None):
        assert es_client
        self.es_client = es_client
        self.last_started = start_time
        self.updates_send = update_send
        self.request = traced_req
        self.max_sleep_secs = max_sleep_secs
        self.spans_seen = {traced_req.span_id}
        self.query = Q("match", traceID=traced_req.trace_id) & Q("match", operationName=op_name) if op_name else \
            Q("match", traceID=traced_req.trace_id)

    @property
    def update(self):
        return None

    def send_update(self):
        if self.update:
            try:
                self.updates_send.send_nowait(self.update)
            except trio.WouldBlock:
                pass  # ignore

    @abstractmethod
    def update_request(self, result: Dict[str, Any]):
        # update this request with the latest result data;
        # specifically, if self.request.latency > 0 then this task will end
        pass

    async def search_loop(self):
        last_search_time = self.last_started
        while True:
            # 1) check whether PR has expired -> if so, mark and leave loop
            if self.request.expiration:
                if self.request.expiration < dt.datetime.utcnow():
                    break
                sleep_time = min(random.random()*self.max_sleep_secs,
                                 math.ceil((self.request.expiration - dt.datetime.utcnow()).total_seconds()))
            else:
                sleep_time = random.random() * self.max_sleep_secs
            # 2) execute ES search for trace ID & any other required matches:
            #    if new information then add to this request, possibly calculate overall latency (also stop there)
            updated = False
            search_results = self.es_client.execute_search(
                {"gt": last_search_time},
                ["startTimeMillis",
                 "operationName",
                 "process.serviceName",
                 "process.tags", "tags",
                 "traceID", "spanID"],
                self.query)
            for result in search_results:
                pre_len = len(self.spans_seen)  # use length of spans to avoid lookup in case set gets big
                self.spans_seen.add(result['spanID'])
                if pre_len == len(self.spans_seen):
                    continue  # span ID was already present in set
                updated = True
                self.update_request(result)
            if updated:
                self.send_update()  # notify dashboard of updates
            if self.request.latency:
                break  # we found the end of the poll request
            if len(search_results):
                last_search_time = search_results[-1]['startTimeMillis'] - 1  # results are sorted by start time
            # 3) sleep before checking again
            await trio.sleep(sleep_time)
        # sleep until expiration (if given), otherwise silently finish
        if self.request.expiration:
            sleep_time = max(0, math.ceil((self.request.expiration - dt.datetime.utcnow()).total_seconds()) + 1)
            await trio.sleep(sleep_time)
            self.send_update()  # notify dashboard of expiry


def filter_tr_factory(kv_pairs):
    return {k: v for k, v in kv_pairs if k not in ['span_id', 'expiration']}
