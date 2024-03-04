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
from typing import Dict


class FloodDB:
    database: Dict[bytes, int]

    def __init__(self):
        self.database = {}

    def update(self, flood_id: bytes, hop_count: int) -> bool:
        if flood_id not in self.database:
            self.database[flood_id] = hop_count
            return True

        if hop_count < self.database[flood_id]:
            self.database[flood_id] = hop_count
            return True

        return False

    # TODO - tag entries with last-updated and purge old entries to save memory
