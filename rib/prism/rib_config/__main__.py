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
import sys

from prism.config.config import Configuration
from prism.config.error import ConfigError
from prism.config.generate import run
from prism.config.ibe import create_ibe
from .channel import CHANNEL_TAGS

from .deployment import RIBDeployment
from .args import parser
from .link_negotiation import link_fulfillment_complete, generation_status

args = parser.parse_args()


def generate_config():
    for channel_tags in args.channel_tags:
        channel, tags = channel_tags.split("=")
        if tags:
            tags = tags.split(",")
        else:
            tags = []
        CHANNEL_TAGS[channel] = tags

    deployment = RIBDeployment(
        config_file=args.range_config_file,
        output_path=args.config_dir,
        channels_path=args.channel_list,
        fulfilled_links_path=args.fulfilled_requests,
    )

    try:
        if deployment.output_path.exists() and not args.overwrite:
            print("Config directory already exists and --overwrite not specified. Aborting.")
            sys.exit(1)

        deployment.output_path.mkdir(parents=True, exist_ok=True)

        if args.fulfilled_requests:
            if not link_fulfillment_complete(deployment.requested_links, deployment.fulfilled_links):
                raise ConfigError("Not enough links succeeded.")
            deployment.write_status(generation_status(deployment.status_path, True, "success"))
            return

        config = Configuration.load_args(args)
        if deployment.channels:
            for channel in deployment.channels:
                config.prism_common[f"channel_{channel.channel_gid}_tags"] = ",".join(channel.tags)

        config.freeze()

        ibe = create_ibe(args.ibe_cache, config.ibe_shards, config.ibe_dir, config.ibe_level)
        deployment.mkdirs()
        run(deployment, ibe, config)

        deployment.write_status(generation_status(deployment.status_path, False, "First round complete."))
    except ConfigError as e:
        print(f"Config generation failed: {e}")
        if not deployment.link_requests_path.exists():
            deployment.link_requests_path.write_text("{}")
        deployment.write_status(generation_status(deployment.status_path, True, f"Failed -- {e}"))


generate_config()
