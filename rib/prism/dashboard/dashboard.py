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
from datetime import datetime
import math
from pathlib import Path
import structlog
import trio

from .es_queries.QT_alive import AliveQuery
from .es_queries.QT_bootstrap import BootstrapQuery, BootstrapRequest
from .es_queries.QT_databases import DatabasesQuery
from .es_queries.active_br_query import ActiveBootstrapRequestsTask
from .es_queries.active_pr_query import ActivePollRequestsTask
from .es_queries.es_client import ESClientTrioAware
from .es_queries.QT_network import NetworkQuery
from .es_queries.QT_poll_requests import PollRequestsQuery, PollRequest
from .es_queries.QT_send_receive import SendReceiveQuery
from .reporter import PrintReporter


class Dashboard:
    """The main class. Orchestrates subtasks for querying Elasticsearch."""

    def __init__(self, **kwargs):
        # self.args = args
        self.es_address = f"{kwargs['es_host']}:{kwargs['es_port']}"
        self.http_proxy = f"socks5://{kwargs['http_proxy']}" if kwargs['http_proxy'] else ""
        print(f"Using ES at {self.es_address}" + (f" with {self.http_proxy}" if self.http_proxy else ""))
        self.last_start_time = kwargs['start_time']
        self.started_at = datetime.fromtimestamp(float(kwargs['start_time'] / 1000)) \
            if kwargs['start_time'] > 0 else datetime.now()
        self.gui = kwargs['gui']
        self.jaeger = kwargs['jaeger_host'] if kwargs['jaeger_host'] else kwargs['es_host']
        self.es_sleeps = kwargs['es_sleeps']
        self.epoch = kwargs['epoch']
        self.verbose = kwargs['verbose']

    # async def track_poll_requests_loop(self, receive_ch: trio.MemoryReceiveChannel,
    #                                    update_ch: trio.MemorySendChannel, es_client: ESClientTrioAware):
    #     async with trio.open_nursery() as nursery:
    #         async with receive_ch:
    #             async for trigger_element in receive_ch:
    #                 assert isinstance(trigger_element, PollRequest)
    #                 nursery.start_soon(ActivePollRequestsTask(es_client, self.last_start_time, update_ch,
    #                                                           trigger_element).search_loop)

    async def traced_requests_loop(self, receive_ch: trio.MemoryReceiveChannel, es_client: ESClientTrioAware,
                                   pr_update: trio.MemorySendChannel, br_update: trio.MemorySendChannel):
        async with trio.open_nursery() as nursery:
            async with receive_ch:
                async for trigger_element in receive_ch:
                    if isinstance(trigger_element, PollRequest):
                        nursery.start_soon(ActivePollRequestsTask(es_client, self.last_start_time, trigger_element,
                                                                  pr_update)
                                           .search_loop)
                    elif isinstance(trigger_element, BootstrapRequest):
                        nursery.start_soon(ActiveBootstrapRequestsTask(es_client, self.last_start_time, trigger_element,
                                                                       br_update)
                                           .search_loop)
                    else:
                        structlog.get_logger("prism").warning(f"Cannot use trigger element {trigger_element}")

    async def run(self):
        print(f"Started at {self.started_at}")

        es_client = ESClientTrioAware(self.es_address, self.http_proxy)

        net_updates, net_updates_recv = trio.open_memory_channel(math.inf)  # in case we need buffering
        net_query = NetworkQuery(net_updates_recv, es_client, self.last_start_time, self.es_sleeps[0], "tags",
                                 epoch=self.epoch, verbose=self.verbose) if self.es_sleeps[0] > 0 else None

        trigger_send, trigger_recv = trio.open_memory_channel(math.inf)  # in case we need buffering
        # transmission_task = TransmissionQuery(es_client, self.last_start_time, trigger_recv, self.verbose)

        pr_update_send, pr_update_recv = trio.open_memory_channel(math.inf)  # in case we need buffering
        pr_query = PollRequestsQuery(trigger_send.clone() if self.verbose else None,
                                     net_updates.clone(), pr_update_recv, self.jaeger,
                                     es_client, self.last_start_time, self.es_sleeps[3], "logs", "tags")
        br_update_send, br_update_recv = trio.open_memory_channel(math.inf)  # in case we need buffering
        br_query = BootstrapQuery(trigger_send.clone(), self.jaeger, br_update_recv,
                                  es_client, self.last_start_time, self.es_sleeps[5], "tags")

        query_tasks = [
            net_query,
            DatabasesQuery(net_query, es_client, self.last_start_time, self.es_sleeps[1], "tags",
                           epoch=self.epoch) if self.es_sleeps[1] > 0 else None,
            SendReceiveQuery(self.jaeger, es_client, self.last_start_time, self.es_sleeps[2], "tags",
                             epoch=self.epoch) if self.es_sleeps[2] > 0 else None,
            pr_query if self.es_sleeps[3] > 0 else None,
            br_query if self.es_sleeps[5] > 0 else None,
        ]
        # this query is just feeding to net_query and does not report to GUI or terminal:
        alive_query = AliveQuery(net_updates.clone(), es_client, self.last_start_time, self.es_sleeps[4], "tags",) \
            if self.es_sleeps[4] > 0 else None

        # add transmission task to PrintReporter and GUI backend:
        reporter = PrintReporter(query_tasks, clear=not self.gui)
        async with trio.open_nursery() as nursery:
            # nursery.start_soon(transmission_task.trigger_loop)
            nursery.start_soon(self.traced_requests_loop, trigger_recv, es_client, pr_update_send, br_update_send)
            nursery.start_soon(pr_query.process_active_prs)
            nursery.start_soon(br_query.process_active_reqs)
            for qt in query_tasks + [alive_query]:
                if qt:
                    nursery.start_soon(qt.start_soon, nursery)
            if self.gui:
                from .gui.backend import run_api
                nursery.start_soon(run_api, nursery, self.jaeger, tuple(query_tasks))
                # TODO: spin up separate Python process for Streamlit?
                path = Path(__file__)
                print(f"\n ~~~ \nPlease start Streamlit from VENV in {path.parent} using something like this:")
                print("  (venv)$ python -m streamlit run gui/dash_st.py\n ~~~\n")
            else:
                nursery.start_soon(reporter.run)
