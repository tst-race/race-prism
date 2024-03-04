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

from ..command import RIBCommand


class Override(RIBCommand):
    """Override a config parameter for the active deployment."""

    aliases = ["o"]

    overrides: List[str] = None

    def run(self):
        d = self.ensure_current()
        if not self.overrides:
            d.overrides.clear()

        for o in self.overrides:
            k, v = o.split("=")
            d.overrides[k] = v

        d.save()

    @classmethod
    def extend_parser(cls, parser):
        parser.add_argument(
            "overrides",
            metavar="X=Y",
            nargs="*",
            help="Config variables to override for this deployment.\nLeave blank to clear overrides.",
        )
