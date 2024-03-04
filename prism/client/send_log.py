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
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from queue import Queue, Empty
from typing import List, Optional

from prism.client.routing import MessageRoute
from prism.client.server_db import ServerDB, ServerRecord
from prism.common.cleartext import ClearText
from prism.common.config import configuration
from prism.common.logging import get_logger


@dataclass
class SendLogEntry:
    message: ClearText
    routes_sent: List[MessageRoute] = field(default_factory=list)

    @property
    def dropboxes_sent(self) -> List[ServerRecord]:
        return [route.target for route in self.routes_sent]

    @property
    def sends_remaining(self) -> int:
        return configuration.dropbox_send_redundancy - len(self.dropboxes_sent)

    @property
    def finished(self) -> bool:
        return self.sends_remaining < 1

    @property
    def last_sent(self) -> Optional[datetime]:
        if self.routes_sent:
            return max(route.timestamp for route in self.routes_sent)
        else:
            return None

    def __str__(self):
        return f"MessageLog.Entry({self.message.trace_id})"

    def targets(self, candidates: List[ServerRecord]) -> List[ServerRecord]:
        return [candidate for candidate in candidates if candidate not in self.dropboxes_sent]

    def sent(self, route: MessageRoute):
        self.routes_sent.append(route)

    def invalidate_routes(self, server_db: ServerDB):
        self.routes_sent = [route for route in self.routes_sent if not route.is_dead(server_db)]

    @property
    def safe(self) -> bool:
        if not self.finished:
            return False

        threshold = timedelta(seconds=configuration.client_retain_message_sec)
        interval = datetime.utcnow() - self.last_sent
        return interval > threshold


class SendLog:
    def __init__(self, server_db: ServerDB):
        self.server_db = server_db
        self.backlog: Queue[SendLogEntry] = Queue()
        self.complete: List[SendLogEntry] = []
        self.logger = get_logger(__name__)

    def add(self, message: ClearText):
        self.backlog.put(SendLogEntry(message))

    @contextmanager
    def attempt(self):
        self.cleanup_complete()

        try:
            entry = self.backlog.get_nowait()
        except Empty:
            yield None
            return
        entry.invalidate_routes(self.server_db)

        yield entry

        if entry.finished:
            self.complete.append(entry)
        else:
            self.backlog.put(entry)

    def cleanup_complete(self):
        for entry in self.complete:
            entry.invalidate_routes(self.server_db)
            if not entry.finished:
                self.logger.warn(f"SendLog entry {entry} invalidated by dead server on route, returning to queue")
                self.backlog.put(entry)

        self.complete = [entry for entry in self.complete if entry.finished and not entry.safe]

    def empty(self):
        return self.backlog.empty()

    def __len__(self):
        return self.backlog.qsize()
