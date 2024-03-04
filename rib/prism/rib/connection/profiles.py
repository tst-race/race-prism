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
from __future__ import annotations
import json
from typing import List, Dict

from prism.common.epoch.genesis import LinkProfile
from networkManagerPluginBindings import IRaceSdkNM


def load_profiles(race: IRaceSdkNM) -> Dict[str, List[LinkProfile]]:
    """
    Load genesis link profiles from a file, returning a dictionary of this node's genesis links for each channel
    """
    profile_text = bytes(race.readFile("link-profiles.json")).decode("utf-8")

    if not profile_text:
        return {}

    profiles = json.loads(profile_text)

    return {
        channel: [LinkProfile.from_dict(channel, profile) for profile in profiles]
        for channel, profiles in profiles.items()
    }
