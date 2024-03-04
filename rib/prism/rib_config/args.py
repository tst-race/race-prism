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
import argparse

parser = argparse.ArgumentParser(description="Generate RACE Config Files")
required = parser.add_argument_group("Required Arguments")
optional = parser.add_argument_group("Optional Arguments")

# Required Arguments
required.add_argument(
    "--range",
    dest="range_config_file",
    help="Range config of the physical network",
    required=True,
    type=str,
)
optional.add_argument(
    "--config-dir",
    dest="config_dir",
    help="Where should configs be stored",
    required=True,
    default="./configs",
    type=str,
)

# Optional Arguments
optional.add_argument(
    "--ibe-cache",
    dest="ibe_cache",
    help="A cache of pregenerated IBE keys containing all client names needed for the range.",
    required=False,
    default=None,
    type=str,
)
optional.add_argument(
    "--overwrite",
    dest="overwrite",
    help="Overwrite configs if they exist",
    required=False,
    default=False,
    action="store_true",
)
optional.add_argument(
    "--local",
    dest="local_override",
    help=(
        "Ignore range config service connectivity, utilized "
        "local configs (e.g. local hostname/port vs range services fields). "
        "Does nothing for Direct Links at the moment"
    ),
    required=False,
    default=False,
    action="store_true",
)
optional.add_argument(
    "--channel-list",
    dest="channel_list",
    help="Path to a JSON file with a list of available comms channels and their properties.",
    required=False,
    type=str,
)
optional.add_argument(
    "--fulfilled-requests",
    dest="fulfilled_requests",
    help="Path to a list of fulfilled link requests.",
    required=False,
    type=str,
)
optional.add_argument(
    "--param",
    "-P",
    metavar="PARAM=VALUE",
    action="append",
    dest="param_overrides",
    default=[],
    help="Override a config parameter. May be specified multiple times.\nExample: -Ptopology=SPARSE_ROUTED",
)
optional.add_argument(
    "--tags",
    "-T",
    metavar="CHANNEL=[ROLE[,ROLE[...]]]",
    action="append",
    dest="channel_tags",
    default=[],
    help="Override the roles for a given channel.\nExample: -TtwoSixDirectcpp=mpc,lsp",
)

parser.add_argument(
    "json_configs", metavar="JSON", type=argparse.FileType("r"), nargs="*", help="JSON configuration files."
)
