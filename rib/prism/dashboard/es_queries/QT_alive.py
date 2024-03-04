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
from opensearch_dsl import Q
import structlog
import trio
from typing import *

from .query_task import LimitedESQuery
from .QT_network import AliveEvent

ALIVE_LOOKBACK = 21.0


class AliveQuery(LimitedESQuery):

    def __init__(self, recv_results: trio.MemorySendChannel, *args, **kwargs):
        super().__init__(ALIVE_LOOKBACK,
                         Q("match", operationName="alive-loop") | Q("match", operationName="monitor-client"),
                         *args, **kwargs)
        self.recv_results = recv_results
        if self.es_sleep <= ALIVE_LOOKBACK:
            structlog.get_logger("prism")\
                .warning(f"Alive Task sleeps {self.es_sleep:.1f}s but LOOKBACK = {ALIVE_LOOKBACK}s...")

    def __str__(self):
        return ""

    def get_data(self, **kwargs):
        return {}

    def process_search_results(self, search_results: List) -> bool:
        known_traces = {}  # type: Dict[Tuple[str, str, str], AliveEvent]
        for result in search_results:
            name = [tag["value"] for tag in result['process']['tags'] if tag["key"] == "hostname"][0]
            epoch = [tag["value"] for tag in result['tags'] if tag["key"] == "epoch"][0]
            known_traces[(name, result["operationName"], epoch)] = AliveEvent(
                name, result["operationName"], epoch, result["startTimeMillis"])
        if self.recv_results:
            try:
                self.recv_results.send_nowait(list(known_traces.values()))
            except trio.WouldBlock:
                pass  # ignore
        return False  # never trigger an update because the NetworkQuery task is handling those
