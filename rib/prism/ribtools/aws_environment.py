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
from pathlib import Path
from typing import List, Optional

from prism.ribtools.environment import environment


@dataclass
class AWSEnvironment:
    name: str = field()
    network_manager_plugin: str = field(default="prism:latest:dev")
    ssh_key: str = field(default="sri_prism_rangekey")
    service_instance_type: str = field(default="t3a.2xlarge")
    linux_instance_type: str = field(default="r5.12xlarge")
    linux_instance_count: int = field(default=4)
    rib_flags: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        s = (
            f"AWSEnvironment: {self.name}\n"
            f"linux_instance_count: {self.linux_instance_count}\n"
            f"linux_instance_type: {self.linux_instance_type}\n"
            f"service_instance_type: {self.service_instance_type}\n"
            f"network_manager_plugin: {self.network_manager_plugin}\n"
        )

        if self.rib_flags:
            s += "\nCustom RIB flags:\n"
            for flag in self.rib_flags:
                s += f"  {flag}\n"

        return s

    def bastion_ip(self, name: str = "service-host") -> Optional[str]:
        cache_file = self.path() / "aws_env_cache.json"
        if not cache_file.exists():
            print(f"Couldn't find aws env cache at {cache_file}")
            return None
        j = json.loads(cache_file.read_text())
        if not j:
            print("Couldn't load JSON from aws env cache.")
            return None
        service_hosts = j.get("instances", {}).get(name, [])
        if not service_hosts:
            print(f"Couldn't find {name} key in json: {j}")
            return None
        return service_hosts[0]

    def path(self) -> Path:
        return environment.rib_dir / "aws-envs" / self.name

    def to_json(self) -> dict:
        d = copy(self.__dict__)
        return d

    def save(self, save_path: Optional[Path] = None):
        if not save_path:
            save_path = self.storage_path(self.name)

        j = json.dumps(self.to_json(), indent=2)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(j)

    def is_current(self) -> bool:
        if environment.current_environment_path.exists():
            current_name = environment.current_environment_path.read_text().strip()
            return self.name == current_name
        else:
            return False

    def make_current(self):
        environment.current_environment_path.write_text(self.name)

    def is_created(self) -> bool:
        return self.path().exists()

    @staticmethod
    def storage_path(name: str) -> Path:
        return environment.environments_dir / f"{name}.json"

    @staticmethod
    def exists(name: str) -> bool:
        return AWSEnvironment.storage_path(name).exists()

    @classmethod
    def load(cls, j: dict) -> AWSEnvironment:
        j = {k: v for k, v in j.items() if k in inspect.signature(cls).parameters}
        return AWSEnvironment(**j)

    @staticmethod
    def load_named(name: str) -> Optional[AWSEnvironment]:
        return AWSEnvironment.load_path(AWSEnvironment.storage_path(name))

    @staticmethod
    def load_path(path: Path) -> Optional[AWSEnvironment]:
        if path.exists():
            try:
                return AWSEnvironment.load(json.loads(path.read_text()))
            except json.decoder.JSONDecodeError:
                print(f"File {path.absolute()} is not valid JSON - please edit")
        return None

    @staticmethod
    def current() -> Optional[AWSEnvironment]:
        if not environment.current_environment_path.exists():
            return None

        current_name = environment.current_environment_path.read_text().strip()
        return AWSEnvironment.load_named(current_name)
