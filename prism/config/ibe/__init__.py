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
from typing import Optional

from prism.config.error import ConfigError
from prism.config.ibe.cached import CachedIBE
from prism.config.ibe.generated import GeneratedIBE
from prism.config.ibe.ibe import IBE


def create_ibe(ibe_cache: Optional[str], ibe_shards: int, ibe_dir: Optional[str], ibe_level: Optional[int]) -> IBE:
    if ibe_cache:
        cache_path = Path(f"{ibe_cache}-{ibe_shards}")
        if not cache_path.exists():
            raise ConfigError(f"IBE cache at path {cache_path} not found. Try using 1 or 3 IBE shards.")
        cache = json.loads(cache_path.read_text())
        return CachedIBE(ibe_shards, cache)
    else:
        return GeneratedIBE(ibe_shards, ibe_dir, ibe_level)
