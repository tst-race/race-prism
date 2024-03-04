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
import os

from prism.ribtools.error import PRTError

from ...command import RIBCommand


class Edit(RIBCommand):
    """Edit a parameter of the active environment."""

    aliases = ["e"]

    key: str = None
    value: str = None

    def run(self):
        e = self.ensure_aws()

        if not self.key:
            editor = os.environ["EDITOR"].split()
            self.subprocess([*editor, e.storage_path(e.name)])
            return

        if not hasattr(e, self.key):
            raise PRTError(f"Unknown parameter {self.key}. Valid parameters are {vars(e).keys()}")

        old_value = getattr(e, self.key)
        if isinstance(old_value, list):
            new_value = list(self.value.split(","))
        else:
            new_value = type(old_value)(self.value)
        setattr(e, self.key, new_value)
        e.save()

    @classmethod
    def extend_parser(cls, parser):
        parser.add_argument("key", metavar="KEY", nargs="?")
        parser.add_argument("value", metavar="VALUE", nargs="?")
