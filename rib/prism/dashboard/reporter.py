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
import os
import trio
from typing import List, Union
from .es_queries.query_task import PeriodicESQuery

UPDATE_SECONDS = 1  # how often to update this report TODO: make configurable?


class PrintReporter:
    """Prints the latest report to stdout on a specified interval."""

    def __init__(self, tasks: List[PeriodicESQuery], clear=True):
        self.tasks = [task for task in tasks if task]
        self.clear = clear

    async def run(self):
        if self.clear:
            while True:
                print('\n'.join([str(qt) for qt in self.tasks]))
                await trio.sleep(UPDATE_SECONDS)
                os.system("clear")
        else:
            last_seqnos = {}
            while True:
                current_seqnos = {qt.__class__.__name__: qt.seqno_update for qt in self.tasks}
                if last_seqnos != current_seqnos:  # anything new?
                    print('\n'.join([str(qt) for qt in self.tasks]))
                last_seqnos = current_seqnos
                await trio.sleep(UPDATE_SECONDS)
