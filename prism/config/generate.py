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
import random

from prism.config.config import Configuration
from prism.config.environment import Deployment
from prism.config.ibe.ibe import IBE


def run(deployment: Deployment, ibe: IBE, config: Configuration):
    if config.random_seed:
        random.seed(config.random_seed)

    try:
        deployment.mkdirs()
        if config.sortition == "STATIC":
            deployment.range.assign_roles(config, ibe)
        elif config.sortition == "VRF":
            deployment.range.perform_sortition(config, ibe)
        elif config.sortition == "DUMMIES":
            deployment.range.genesis_dummies(config, ibe)
        else:
            print(f"Don't understand config sortition mode={config.sortition} - aborting!")
            return
        deployment.range.configure_roles(config, ibe)
        deployment.range.configure_topology(config)

        errors = deployment.check(config)
        if errors:
            for error in errors:
                print(error)
                print()
            print(f"Found {len(errors)} errors that prevent config generation:")
            return

        deployment.save(config)
    finally:
        if not config.ibe_dir:
            ibe.cleanup()
