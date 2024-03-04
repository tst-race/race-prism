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
import bisect
from opensearch_dsl import Q
import trio
from typing import *

from .es_client import ESClientTrioAware
from .QT_bootstrap import BootstrapRequest
from .trace_id_query import TracingIdTask


class ActiveBootstrapRequestsTask(TracingIdTask):

    def __init__(self, es_client: ESClientTrioAware, start_time: int, bootstrap_request: BootstrapRequest,
                 update_send: trio.MemorySendChannel):
        super().__init__(es_client, start_time, bootstrap_request.traced_req, update_send, 15)
        self.query = Q("match", traceID=f"{bootstrap_request.traced_req.trace_id}") & (
                Q("match", operationName="bootstrap-receive") |
                Q("match", operationName="send-message") |
                Q("match", operationName="receive-message") |
                Q("match", operationName="client-registration-response"))
        self.augmented_request = bootstrap_request

    @property
    def update(self):
        return self.augmented_request

    def update_request(self, result: Dict[str, Any]):
        name = [tag["value"] for tag in result['process']['tags'] if tag["key"] == "hostname"][0]
        current_end = int(result['startTimeMillis'])

        if current_end > self.augmented_request.end_time_ms:
            self.augmented_request.end_time_ms = current_end
            self.augmented_request.in_transit_latency = \
                float(self.augmented_request.end_time_ms - self.augmented_request.traced_req.start_time_ms) / 1000
            if result["operationName"] == "bootstrap-receive":
                self.augmented_request.traced_req.latency = \
                    float(self.augmented_request.end_time_ms - self.augmented_request.traced_req.start_time_ms) / 1000
