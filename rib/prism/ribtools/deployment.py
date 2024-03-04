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

import inspect
import json
from copy import copy
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Dict, List, Optional

from prism.ribtools.environment import environment


class DeploymentMode(Enum):
    local = auto()
    aws = auto()
    bastion = auto()


@dataclass
class Deployment:
    name: str = field()
    mode: DeploymentMode = field(default=DeploymentMode.local)
    overrides: Dict[str, str] = field(default_factory=dict)
    client_count: int = field(default=2)
    client_image: str = field(default="")
    android_client_count: int = field(default=0)
    android_image: str = field(default="")
    server_count: int = field(default=4)
    server_image: int = field(default="")
    range_file: Optional[Path] = field(default=None)
    artifact: str = field(default="prism:/code/release")
    comms_channels: List[str] = field(default_factory=lambda: ["twoSixIndirectCpp", "twoSixDirectCpp"])
    rib_flags: List[str] = field(default_factory=list)
    custom_tags: Dict[str, List[str]] = field(default_factory=dict)
    bootstrap_client_count: int = field(default=0)
    bootstrap_android_client_count: int = field(default=0)
    comms_custom_dir: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if self.mode == DeploymentMode.aws:
            self.client_image = self.client_image
            self.server_image = self.server_image

    def __str__(self) -> str:
        s = f"Deployment: {self.name}\n" f"mode: {self.mode.name}\n"

        if self.range_file:
            s += f"range_file: {self.range_file}\n"
        else:
            s += f"client_count: {self.client_count - self.bootstrap_client_count}"
            if self.bootstrap_client_count:
                s += f" (+{self.bootstrap_client_count} uninstalled) "
            if self.client_image:
                s += f" ({self.client_image})"
            s += "\n"
            s += f"android_client_count: {self.android_client_count - self.bootstrap_android_client_count}"
            if self.bootstrap_android_client_count:
                s += f" (+{self.bootstrap_android_client_count} uninstalled) "
            if self.android_image:
                s += f" ({self.android_image})"
            s += "\n"
            s += f"server_count: {self.server_count}"
            if self.server_image:
                s += f" ({self.server_image})"
            s += "\n"
        s += (
            f"Prism Plugin: {self.artifact}\n"
            f"Comms Channels: {', '.join(self.comms_channels)}\n"
        )

        if self.rib_flags:
            s += "\nCustom RIB flags:\n"
            for flag in self.rib_flags:
                s += f"  {flag}\n"

        if self.overrides:
            s += "\nParameter overrides:\n"

            for k, v in self.overrides.items():
                s += f"  {k} = {v}\n"

        if self.custom_tags:
            s += "\nCustom channel tags:\n"

            for k, v in self.custom_tags.items():
                s += f"  {k} = {v}\n"

        if self.comms_custom_dir:
            s += "\nCustom Comms args:\n"
            for k, v in self.comms_custom_dir.items():
                s += f"  {k} = {v}\n"

        return s

    @property
    def custom_args(self):
        custom_args = []
        if self.overrides:
            custom_args.extend([f"-P{k}={v}" for k, v in self.overrides.items()])
        if self.custom_tags:
            custom_args.extend([f"-T{k}={','.join(v)}" for k, v in self.custom_tags.items()])
        return custom_args

    def path(self) -> Path:
        return environment.rib_dir / "deployments" / self.mode.name / self.name

    def config_path(self) -> Path:
        return self.path() / "configs" / "network-manager" / "prism"

    def log_path(self) -> Path:
        return self.path() / "logs"

    def to_json(self) -> dict:
        d = copy(self.__dict__)
        d["mode"] = self.mode.name
        if self.range_file:
            d["range_file"] = str(self.range_file)
        return d

    def save(self, save_path: Optional[Path] = None):
        if not save_path:
            save_path = self.storage_path(self.name)

        j = json.dumps(self.to_json(), indent=2)
        save_path.write_text(j)

    def is_current(self) -> bool:
        if environment.current_deployment_path.exists():
            current_name = environment.current_deployment_path.read_text().strip()
            return self.name == current_name
        else:
            return False

    def make_current(self):
        environment.current_deployment_path.write_text(self.name)

    def is_created(self) -> bool:
        return self.path().exists()

    @staticmethod
    def storage_path(name: str) -> Path:
        return environment.deployments_dir / f"{name}.json"

    @staticmethod
    def exists(name: str) -> bool:
        return Deployment.storage_path(name).exists()

    @classmethod
    def load(cls, j: dict) -> Deployment:
        j = {k: v for k, v in j.items() if k in inspect.signature(cls).parameters}
        j["mode"] = DeploymentMode[j["mode"]]
        if j.get("range_file"):
            j["range_file"] = Path(j["range_file"])
        return Deployment(**j)

    @staticmethod
    def load_named(name: str) -> Optional[Deployment]:
        return Deployment.load_path(Deployment.storage_path(name))

    @staticmethod
    def load_path(path: Path) -> Optional[Deployment]:
        if path.exists():
            try:
                return Deployment.load(json.loads(path.read_text()))
            except json.decoder.JSONDecodeError:
                print(f"File {path.absolute()} is not valid JSON - please edit")
        return None

    @staticmethod
    def current() -> Optional[Deployment]:
        if not environment.current_deployment_path.exists():
            return None

        current_name = environment.current_deployment_path.read_text().strip()
        return Deployment.load_named(current_name)

    def total_clients(self) -> int:
        return self.client_count + self.android_client_count
