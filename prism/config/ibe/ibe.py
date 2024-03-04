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
from typing import List

MIN_SECURE_LEVEL = 3


class IBE:
    registrar_name: str = "prism_client_registration"
    public_params: str
    public_param_shards: List[str]
    ibe_secrets: List[str]
    shards: int

    def node_config(self, name) -> dict:
        return {
            "name": name,
            "private_key": self.private_key(name),
        }

    def private_key(self, name: str) -> str:
        pass

    def cleanup(self):
        pass
