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

from abc import ABCMeta, abstractmethod
from pathlib import Path
from typing import Optional

from prism.common.config import configuration


class StateStore(metaclass=ABCMeta):
    @abstractmethod
    def save_state(self, name: str, state: dict):
        pass

    @abstractmethod
    def load_state(self, name: str) -> Optional[dict]:
        pass


class DummyStateStore(StateStore):
    def __init__(self):
        super().__init__()
        self.state = {}

    def save_state(self, name: str, state: dict):
        self.state[name] = state

    def load_state(self, name: str) -> Optional[dict]:
        return self.state.get(name, None)


class DirectoryStateStore(StateStore):
    def __init__(self, state_path: Path):
        super().__init__()
        self.state_path = state_path
        self.state_path.mkdir(exist_ok=True)

    def save_path(self, name: str) -> Path:
        return self.state_path / f"{name}.json"

    def save_state(self, name: str, state: dict):
        self.save_path(name).write_text(json.dumps(state))

    def load_state(self, name: str) -> Optional[dict]:
        if configuration.ignore_state:
            return None

        if not self.save_path(name).exists():
            return None

        return json.loads(self.save_path(name).read_text())


class EpochStateStore(StateStore):
    def __init__(self, inner_store: StateStore, epoch: str):
        self.inner_store = inner_store
        self.epoch = epoch

    def _transform_name(self, name: str):
        return f"epoch_{self.epoch}_{name}"

    def save_state(self, name: str, state: dict):
        self.inner_store.save_state(self._transform_name(name), state)

    def load_state(self, name: str) -> Optional[dict]:
        return self.inner_store.load_state(self._transform_name(name))
