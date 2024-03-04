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
import re

from prism.ribtools.error import PRTError


shorthand_regex = re.compile(r"^(?P<scope>[csg])(?P<node_num>[0-9]*)(?P<suffix>[a-z]*)$")


def race_name(node_type: str, node_num: int) -> str:
    return f"race-{node_type}-{node_num:05}"


def shorthand_to_node(shorthand: str) -> str:
    match = shorthand_regex.match(shorthand)
    if not match:
        raise PRTError(f"Invalid shorthand {shorthand}")

    groups = match.groupdict()
    node_type = "client" if groups["scope"] == "c" else "server"
    node_num = int(groups["node_num"])
    return race_name(node_type, node_num)
