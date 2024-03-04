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
from pathlib import Path
from typing import List

from prism.common.crypto.ibe import BonehFranklin
from prism.config.error import ConfigError
from prism.config.ibe.ibe import IBE, MIN_SECURE_LEVEL


class GeneratedIBE(IBE):
    def __init__(self, shards: int, path=None, requested_security=MIN_SECURE_LEVEL):
        if path:
            self.path = Path(path)
        else:
            self.path = None

        self.shards = shards
        self.ibe_shards = self.generate(shards, requested_security)
        self.public_param_shards = [ibe.public_params for ibe in self.ibe_shards]
        self.public_params = BonehFranklin.sum_public(self.public_param_shards)
        self.ibe_secrets = [ibe.system_secret for ibe in self.ibe_shards]

        if requested_security > self.ibe_shards[0].security_level:
            raise ConfigError(f"Loaded IBE system below requested security level ({requested_security})")

    def generate(self, shards: int, security_level) -> List[BonehFranklin]:
        if security_level < MIN_SECURE_LEVEL:
            print(f"WARNING: IBE levels below {MIN_SECURE_LEVEL} are potentially insecure.")

        if self.path is not None and self.path.exists():
            j = json.loads(self.path.read_text())

            return [BonehFranklin.load_generator(param_shard, secret_shard)
                    for param_shard, secret_shard in zip(j["public_param_shards"], j["ibe_secrets"])]

        base_ibe = BonehFranklin.generate(security_level)
        ibe_shards = [BonehFranklin.generate_shard(base_ibe) for _ in range(shards)]
        public_params = BonehFranklin.sum_public([shard.public_params for shard in ibe_shards])
        if self.path is not None:
            j = {
                "public_params": public_params,
                "public_param_shards": [shard.public_params for shard in ibe_shards],
                "system_secret": [shard.system_secret for shard in ibe_shards],
            }
            self.path.write_text(json.dumps(j))

        return ibe_shards

    def private_key(self, name):
        key_shards = [shard.generate_private_key(name) for shard in self.ibe_shards]
        return BonehFranklin.sum_secrets(self.ibe_shards[0].public_params, key_shards)
