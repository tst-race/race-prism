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
from argparse import ArgumentParser

from prism.ribtools.deployment import Deployment

from ..command import RIBCommand


class Info(RIBCommand):
    """Show information about a deployment (by default the active one)."""

    aliases = ["i"]

    deployment_name: str = ""

    def run(self):
        if self.deployment_name:
            d = Deployment.load_named(self.deployment_name)
        else:
            d = self.ensure_current()
        print(d)

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        parser.add_argument("deployment_name", metavar="DEPLOYMENT", nargs="?")
