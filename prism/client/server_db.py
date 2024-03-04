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
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List

import structlog

from prism.common.config import configuration
from prism.common.server_db import ServerDB as CommonServerDB, ServerRecord
from prism.common.state import StateStore


@dataclass
class StatusEvent:
    reachable: bool = field(default=True)
    timestamp: datetime = field(default=datetime.utcfromtimestamp(0))

    def to_json(self) -> dict:
        return {
            "reachable": self.reachable,
            "timestamp": self.timestamp.timestamp()
        }

    @classmethod
    def from_json(cls, j: dict) -> StatusEvent:
        return StatusEvent(j["reachable"], datetime.utcfromtimestamp(j["timestamp"]))


class ServerStatus:
    pseudonym: bytes
    events: Dict[bytes, StatusEvent]

    def __init__(self, pseudonym: bytes):
        self.pseudonym = pseudonym
        self.events = {}

    def __repr__(self):
        return "alive" if self.alive else "dead"

    def update(self, source: bytes, timestamp: datetime, reachable: bool):
        self.events[source] = StatusEvent(reachable, timestamp)

    @property
    def alive(self) -> bool:
        alive = [event for event in self.events.values() if event.reachable]
        dead = [event for event in self.events.values() if not event.reachable]

        if not dead:
            return True
        elif not alive:
            return False
        else:
            newest_alive = max(alive, key=lambda e: e.timestamp).timestamp
            newest_dead = max(dead, key=lambda e: e.timestamp).timestamp
            return newest_alive - timedelta(seconds=configuration.client_believe_alive_interval_sec) > newest_dead

    def to_json(self):
        return {
            "pseudonym": self.pseudonym.hex(),
            "events": {
                source.hex(): event.to_json()
                for source, event in self.events.items()
            }
        }

    @classmethod
    def from_json(cls, status_json: dict) -> ServerStatus:
        status = ServerStatus(bytes.fromhex(status_json["pseudonym"]))
        for source, event_json in status_json["events"].items():
            status.events[bytes.fromhex(source)] = StatusEvent.from_json(event_json)
        return status


class ServerDB(CommonServerDB):
    status_db: Dict[bytes, ServerStatus]

    def __init__(self, state_store: StateStore, epoch: str):
        # Init status_db before super init, because it will be overridden by load()
        self.status_db = {}
        super().__init__(state_store=state_store, epoch=epoch)
        self._logger = structlog.get_logger(__name__)

    @property
    def reachable_servers(self) -> List[ServerRecord]:
        return [server for server in self.valid_servers if self.can_reach(server)]

    @property
    def reachable_emixes(self) -> List[ServerRecord]:
        return [emix for emix in self.valid_emixes if self.can_reach(emix)]

    def update_status(self, source: bytes, pseudonym: bytes, timestamp: datetime, reachable: bool):
        if pseudonym not in self.status_db:
            self.status_db[pseudonym] = ServerStatus(pseudonym)

        current_status = self.status_db.get(pseudonym)

        # Adjust death reports 5 seconds into the future to give them priority over life reports sent
        # in the same timeframe
        if not reachable:
            timestamp = timestamp + timedelta(seconds=5)

        was_alive = str(current_status)
        current_status.update(source, timestamp, reachable)
        is_alive = str(current_status)

        if was_alive != is_alive:
            self._logger.debug(f"{source.hex()[:6]}: {pseudonym.hex()[:6]} "
                               f"was {was_alive}, now {is_alive}")

    def can_reach(self, server: ServerRecord) -> bool:
        if not server.valid():
            return False
        if not configuration.ls_routing:
            return True

        status = self.status_db.get(server.pseudonym)
        return status is None or status.alive

    def to_json(self) -> dict:
        j = super().to_json()
        j["status_db"] = [status.to_json() for status in self.status_db.values()]
        return j

    def load(self, state: dict):
        super().load(state)

        if "status_db" in state:
            saved_status = state["status_db"]
            for status_json in saved_status:
                status = ServerStatus.from_json(status_json)
                self.status_db[status.pseudonym] = status

    def debug_dump(self, logger):
        super().debug_dump(logger)
        logger.debug("Server Status")
        for pseudonym, status in self.status_db.items():
            logger.debug(f"{pseudonym.hex()[:8]}: {status}")
