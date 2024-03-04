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
import math
from opensearch_dsl import Q
from random import random
import time
import trio
from typing import *
from .es_client import ESClientTrioAware

# TODO: make configurable?  Or base on self.es_sleep?
# looking back during next query before the highest time stamp in current results:
LOOK_BACK_ROUNDS = 3  # how often to extend looking back while we have search results
EXTEND_LOOK_BACK = 1000  # ms to reduce during each round of looking back


class PeriodicESQuery:
    """Abstract class for continuous Elasticsearch queries, sleeping when no new records are available.

    Subclasses should implement `process_search_results()` and return whether updates where detected."""

    def __init__(self, query: Q, es_client: ESClientTrioAware, start_time: int, es_sleep: float = 10.0,
                 *additional_src_fields, **kwargs):
        self.es_client = es_client
        assert query
        self.query = query
        self.current_update_seqno = 0
        self.source_fields = [
            "startTimeMillis",
            "operationName",
            "process.serviceName",
            "process.tags",
            # "duration",
            "traceID", "spanID",
            # "logs",
            # "tags",
        ]
        self.source_fields.extend(additional_src_fields)
        self.last_started = start_time
        self.es_sleep = es_sleep
        self.send_ch, self.recv_ch = trio.open_memory_channel(0)

    @property
    def seqno_update(self):
        return self.current_update_seqno

    async def _query_loop(self):
        await trio.sleep(random() * self.es_sleep)

        current_range = {}  # type: Dict[str, int]
        if self.last_started:
            current_range["gt"] = self.last_started - 1000

        last_max = 0
        last_spans = set()  # type: Set[str]
        while self.es_client:
            # this call can take a while but is not longer async because no Trio checkpoint:
            results = self.es_client.execute_search(current_range, self.source_fields, self.query)
            await self.send_ch.send(results)
            if len(results):
                # collect span IDs with max startTimeMillis:
                current_last_max = results[-1]['startTimeMillis']
                current_last_spans = set([r['spanID'] for r in results if r['startTimeMillis'] == current_last_max])
                # current_range["gt"] = results[-1]['startTimeMillis']
                if last_max and current_last_spans == last_spans:
                    # we are closing the look-back window
                    current_range["gt"] = min((current_range["gt"] + EXTEND_LOOK_BACK), last_max)
                else:
                    # must include new results:
                    last_max = current_last_max
                    last_spans = current_last_spans
                    current_range["gt"] = last_max - EXTEND_LOOK_BACK * LOOK_BACK_ROUNDS
            else:
                last_max = 0  # signal that we are starting over from here on (roughly)
                current_range["gt"] = max(current_range["gt"],
                                          math.floor(time.time() * 1000) - 60000)  # 1 minute ago (in milliseconds)
            await trio.sleep(self.es_sleep)

    def process_search_results(self, search_results: List) -> bool:
        """Subclasses must implement this and return True if new data is available."""
        return False

    async def _aggregating(self):
        async with self.recv_ch:
            async for search_results in self.recv_ch:
                if self.process_search_results(search_results):
                    self.current_update_seqno += 1

    def get_data(self, **kwargs):
        """Subclasses override this to provide their latest data set as a dict."""
        return {}

    async def start_soon(self, nursery: trio.Nursery):
        nursery.start_soon(self._aggregating)
        nursery.start_soon(self._query_loop)


class LimitedESQuery(PeriodicESQuery):
    """
    Just be concerned with the last N seconds and don't try to look back any further nor be complete in search results.
    """

    def __init__(self, lookback: float, *args, **kwargs):
        super().__init__(*args, **kwargs)
        assert lookback > 0
        self.lookback = lookback

    async def _query_loop(self):
        await trio.sleep(self.lookback)
        while self.es_client:
            current_range = {"gt": max(self.last_started - 1000,
                                       (math.ceil(time.time() - self.lookback)) * 1000)}  # type: Dict[str, int]
            results = self.es_client.execute_search(current_range, self.source_fields, self.query)
            await self.send_ch.send(results)
            await trio.sleep(self.es_sleep)
