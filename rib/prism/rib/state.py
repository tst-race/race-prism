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
from typing import Optional

from prism.common.config import configuration
from prism.rib.Log import logDebug
from networkManagerPluginBindings import IRaceSdkNM

from prism.common.state import StateStore

CACHE_PREFIX = "cache"
STATE_PREFIX = "state"


class RIBStateStore(StateStore):
    def __init__(self, race: IRaceSdkNM):
        self.race = race
        self.race.makeDir(STATE_PREFIX)

    def save_path(self, name: str) -> str:
        return f"{STATE_PREFIX}/{name}.json"

    def cache_path(self, name: str) -> str:
        return f"{CACHE_PREFIX}/{name}.json"

    def save_state(self, name: str, state: dict):
        if not configuration.get("save_state"):
            return

        state_text = json.dumps(state)
        state_bytes = state_text.encode("utf-8")
        self.race.writeFile(self.save_path(name), state_bytes)

    def json_from_file(self, path: str) -> Optional[dict]:
        logDebug(f"Attempting to load read from {path}")
        state_bytes = self.race.readFile(path)
        if not state_bytes:
            logDebug("Could not find file")
            return None

        logDebug(f"Found {len(state_bytes)} bytes")
        state_text = bytes(state_bytes).decode("utf-8")
        logDebug("Decoded bytes")
        j = json.loads(state_text)
        logDebug(f"Decoded json: {j}")
        return j

    def load_state(self, name: str) -> Optional[dict]:
        if configuration.ignore_state:
            logDebug("Ignoring request to load state due to configuration.ignore_state")
            return None
        logDebug(f"Attempting to load state {name}")
        path = self.save_path(name)
        saved = self.json_from_file(path)
        if saved:
            logDebug("Found saved state")
            return saved

        logDebug(f"No saved state for {name}, looking for cache")
        path = self.cache_path(name)
        cached = self.json_from_file(path)
        return cached
