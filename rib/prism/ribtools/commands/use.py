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
from prism.ribtools.deployment import Deployment
from prism.ribtools.error import PRTError

from ..command import RIBCommand


class Use(RIBCommand):
    """Make a deployment the current active deployment."""

    name: str = None

    def run(self):
        d = Deployment.load_named(self.name)
        if not d:
            raise PRTError(f"Could not find deployment named {self.name}.")
        d.make_current()

    @classmethod
    def extend_parser(cls, parser):
        parser.add_argument("name", metavar="NAME", help="The name of the deployment to activate.")
