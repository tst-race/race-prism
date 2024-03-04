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
import trio
from .es_client import ESClientTrioAware


class TriggeredQuery:

    def __init__(self, es_client: ESClientTrioAware, start_time: int, trigger_ch: trio.MemoryReceiveChannel):
        assert es_client
        self.es_client = es_client
        self.last_started = start_time
        assert trigger_ch
        self.trigger_ch = trigger_ch
        self.current_update_seqno = 0  # increment when new data available

    @property
    def seqno_update(self):
        return self.current_update_seqno

    @abstractmethod
    async def trigger_loop(self):
        pass
