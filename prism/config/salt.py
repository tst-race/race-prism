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
from datetime import datetime
from typing import List

from prism.common.pseudonym import Pseudonym


def optimize_salt(client_names: List[str], dropbox_count: int, dropboxes_per_client: int, seconds_per_step=15) -> str:
    """Tries to find as good a salt for client pseudonym hashes as possible in a reasonable amount of time.
    Every seconds_per_step, reduces the difficulty by increasing the maximum load a dropbox can hold and increasing
    the percentage of dropboxes that are allowed to carry greater than the ideal load."""

    # Proportion to increase load cap each time step
    max_load_slack_per_step = 0.1
    # Proportion to increase overload cap each time step
    max_overload_per_step = dropbox_count / 10

    start_time = datetime.now()
    ideal_load = math.ceil(dropboxes_per_client * len(client_names) / dropbox_count)

    def time_steps() -> int:
        current_time = datetime.now()
        delta = (current_time - start_time).total_seconds()
        return math.floor(delta / seconds_per_step)

    def max_load() -> int:
        return math.ceil(ideal_load * (1 + time_steps() * max_load_slack_per_step))

    def max_overloaded() -> int:
        return math.ceil(max_overload_per_step * time_steps())

    def check(guess: int) -> bool:
        client_pseudos = (Pseudonym.from_address(name, str(guess)) for name in client_names)
        load_cap = max_load()
        overload_cap = max_overloaded()

        dropbox_loads = [0] * dropbox_count
        overloaded = 0

        for client_pseudonym in client_pseudos:
            for i in client_pseudonym.dropbox_indices(dropbox_count, dropboxes_per_client):
                if dropbox_loads[i] == ideal_load:
                    overloaded += 1
                if dropbox_loads[i] == load_cap or overloaded > overload_cap:
                    return False
                dropbox_loads[i] += 1

        return True

    candidate = 1
    while not check(candidate):
        candidate += 1

    return str(candidate)