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
from enum import Enum, auto


class EpochState(Enum):
    # An epoch in the PRE_RUN state creates its epoch receive link, generates an epoch ARK,
    # and requests its ancestor epoch to flood the epoch ARK.
    PRE_RUN = auto()
    # A running epoch builds connections to VRF-selected peers and runs as normal
    RUNNING = auto()
    # A transitioning epoch doesn't buy any unripe bananas
    HANDOFF = auto()
    # An epoch that has ended
    OFF = auto()