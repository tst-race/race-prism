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
import json
from enum import Enum
from fastapi import FastAPI, HTTPException, WebSocket
from hypercorn.config import Config
from hypercorn.trio import serve
import trio
from typing import Dict, Tuple, Union
from ..es_queries.query_task import PeriodicESQuery


class QueryName(str, Enum):
    db_sizes_q = "DatabasesQuery"
    network_q = "NetworkQuery"
    send_recv_q = "SendReceiveQuery"
    poll_req_q = "PollRequestsQuery"
    bootstrap_q = "BootstrapQuery"
    # transmission_q = "TransmissionQuery"


app = FastAPI()
API_PORT = 23456  # TODO to be passed from CLI parameters later?
jaeger_host = ""
queries = {}  # type: Dict[QueryName, Tuple[PeriodicESQuery, int]]


async def run_api(nursery: trio.Nursery, jaeger_ip: str,
                  qtasks: Tuple[PeriodicESQuery, PeriodicESQuery, PeriodicESQuery, PeriodicESQuery, PeriodicESQuery]):
    config = Config()
    config.bind = [f"0.0.0.0:{API_PORT}"]
    print(f"Serving FastAPI at http://0.0.0.0:{API_PORT}")

    global queries
    queries[QueryName.network_q] = qtasks[0], 0
    queries[QueryName.db_sizes_q] = qtasks[1], 0
    queries[QueryName.send_recv_q] = qtasks[2], 0
    queries[QueryName.poll_req_q] = qtasks[3], 0
    queries[QueryName.bootstrap_q] = qtasks[4], 0
    # queries[QueryName.transmission_q] = qtasks[4], 0

    # parse Jaeger host name from ES address:
    global jaeger_host
    jaeger_host = jaeger_ip

    nursery.start_soon(check_for_updates)

    # noinspection PyTypeChecker
    await serve(app, config)


async def check_for_updates():
    global queries
    while True:
        for qname, (qt, last_seqno) in queries.items():
            if qt is None:
                continue
            current_seqno = qt.seqno_update
            if current_seqno != last_seqno:  # anything new?
                queries[qname] = (qt, current_seqno)
        await trio.sleep(0.5)


@app.get("/")
def read_root():
    return {"message": "Welcome to the API for the PRISM ElasticSearch Dashboard"}


@app.get("/jaeger")
def jaeger_host() -> str:
    global jaeger_host
    return jaeger_host


@app.get("/seqnos")
def get_seqnos():
    global queries
    return {qname: seqno for qname, (_, seqno) in queries.items()}


@app.get("/seqno/{name}")
def get_seqno_for(name: QueryName) -> int:
    global queries
    return queries.get(name, (None, 0))[1]


@app.get("/text/{name}")
def get_text_for(name: QueryName) -> str:
    global queries
    if name in queries:
        return str(queries[name][0])
    return ""


@app.get("/data/{name}")
def get_data_for(name: QueryName, epoch: str = "genesis", show_graph: bool = False) -> Dict:
    global queries
    if name in queries:
        # TODO: fix: "ValueError: Out of range float values are not JSON compliant"
        #  when this gets served by FastAPI
        qt = queries[name][0]
        if qt is None:
            return {}
        data = qt.get_data(epoch=epoch, show_graph=show_graph)
        try:
            json.dumps(data)  # check if data is JSON-compliant
        except (ValueError, TypeError):
            return {}
        return data
    return {}
