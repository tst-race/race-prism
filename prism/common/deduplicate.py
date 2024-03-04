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

# Message seen storage for de-duplication:
# - create a unique key for each message seen using PREFIX:<message-hash>
# - keys are expiring with configurable TTL (which gets reset when checking)
# - purging of expired entries happens upon checking (to stay synchronous)

import hashlib
import math
from typing import Union

import structlog
import time
import trio

from prism.common.message import PrismMessage


class MessageDeduplicator:

    def __init__(self, configuration) -> None:
        self._configuration = configuration
        self._database = {}
        self._warn_once = True
        self._logger = structlog.getLogger(__name__)

    def is_msg_new(self, msg: Union[PrismMessage, bytes]) -> bool:
        if not msg:
            return True

        if isinstance(msg, PrismMessage):
            data = msg.encode()
        else:
            data = msg

        msg_hash = hashlib.sha256(data).hexdigest()
        # hash message to create a unique key:
        # key = f'MessageSeen:{hashlib.sha256(msg.clone(debug_info=None).encode()).hexdigest()}'
        key = f'MessageSeen:{msg_hash}'
        # does key exist?  in either case, add it with updated or new TTL:
        expiration_time = self._database.get(key, 0.0)
        now = time.time()
        # if TTL <= 0 then keep forever (= memory leak and WARN once)
        ttl = self._configuration.msg_seen_ttl
        if ttl <= 0 and self._warn_once:
            self._logger.warning(f'Keeping a record FOREVER - possible memory leak!')
            self._warn_once = False
        self._database[key] = now + ttl if ttl > 0 else math.inf
        return expiration_time < now

    async def purge_task(self):
        self._logger.debug(f"Starting loop to purge expired messages seen every {self._configuration.msg_seen_sleep}s")
        while True:
            # remove all data base entries that have expired
            now = time.time()
            to_be_purged = [k for k, expires in self._database.items() if expires <= now]
            for key in to_be_purged:
                self._database.pop(key, None)
            await trio.sleep(self._configuration.msg_seen_sleep)
