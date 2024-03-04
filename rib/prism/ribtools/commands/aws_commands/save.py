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
from pathlib import Path

from ...command import RIBCommand


class Save(RIBCommand):
    """Save the active environment to a file."""

    filename: str = None

    def run(self):
        e = self.ensure_aws()
        save_path = Path(self.filename)
        e.save(save_path)

    @classmethod
    def extend_parser(cls, parser):
        parser.add_argument("filename", metavar="FILE", help="The file to save the environment to.")
