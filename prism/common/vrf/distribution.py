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
import itertools
from bisect import bisect_left
from dataclasses import dataclass
from decimal import Decimal
from typing import *


@dataclass
class VRFConfig:
    seed: Optional[str]
    n_ranges: int
    m_replicas: int
    p_emix: float
    p_off: float

    @classmethod
    def from_config(cls, config: Dict[str, Any]):
        return VRFConfig(
            seed=config.get("vrf_seed", None),
            n_ranges=int(config.get("vrf_n_ranges")),
            m_replicas=int(config.get("vrf_m_replicas")),
            p_emix=float(config.get("vrf_p_emix")),
            p_off=float(config.get("vrf_p_off")),
        )


class VRFDistribution:
    # this is an object that maps some set of roles to the probabilities they are selected
    # note that these distributions are approximate.
    # if you can't partition the space exactly then we cut boundaries between points
    # we also add an extra point on the right size of the range (for simplicity. this can be removed)

    def __init__(self, role_map: Dict[str, Union[float, Decimal]], space: int = (2 ** 256) - 1):
        # space gives the total output space over which this distribution is defined
        #    as an example, space takes an integer L to connote a space of all integers in [0,L]
        if not all(isinstance(role, str) for role in role_map.keys()):
            raise TypeError("roles must be of type string")
        if sum(role_map.values()) != 1:
            raise ValueError("probabilities do not sum to 1")
        for p in role_map.values():
            if not (0 <= p <= 1):
                raise ValueError(f"{p} is not a probability")

        # partitions the domain to delimit the roles
        it_sum = 0
        ubs = []
        for role, prob in role_map.items():
            gap = prob * space
            ubs.append(gap + it_sum)
            it_sum = it_sum + gap
        self.roles = list(role_map.keys())
        self.upper_bounds = ubs
        self.space = space

    def __str__(self):
        return str({"map of upperbounds": [(self.roles[i], self.upper_bounds[i]) for i in range(len(self.roles))],
                    "domain": "[ 0 , " + str(self.space) + " ]"})

    def role(self, payload) -> str:
        # outputs the role for some given payload
        if payload < 0 or payload > self.space:
            raise ValueError("Out of Domain", self.space, payload)
        i = bisect_left(self.upper_bounds, payload)
        return self.roles[i]

    @classmethod
    def role_distribution(cls, config: VRFConfig) -> Tuple[VRFDistribution, Dict[str, Tuple[int, int]]]:
        committees = {}
        for n_range, ordinal in itertools.product(range(1, config.n_ranges + 1),
                                                  range(1, config.m_replicas + 1)):
            key = f'DROPBOX_{n_range}_{ordinal}'
            committees[key] = (n_range, ordinal)

        # Total probability mass of dropboxes
        db_ratio = Decimal(1 - config.p_emix - config.p_off)
        # Probability mass of any given dropbox committee
        db_prob = db_ratio / (config.n_ranges * config.m_replicas)

        role_map = {
            "EMIX": Decimal(0),
            "OFF": Decimal(config.p_off),
            **{key: db_prob for key in committees}
        }

        # Any leftover probability mass is given to EMIXes, to make sure that the
        # probability distribution sums to 1
        role_map["EMIX"] = Decimal(1) - sum(role_map.values())

        return VRFDistribution(role_map), committees

    @classmethod
    def binary_distribution(cls, p: float) -> VRFDistribution:
        p_decimal = Decimal(p)
        not_p_decimal = Decimal(1) - p_decimal
        return VRFDistribution({"True": p_decimal, "False": not_p_decimal})

    @classmethod
    def choice_distribution(cls, items: list) -> VRFDistribution:
        items = [str(item) for item in items]
        assert len(items)
        probs = [Decimal(1/len(items))] * len(items)
        probs[-1] = Decimal(1) - sum(probs[:-1])
        return VRFDistribution({item: prob for item, prob in zip(items, probs)})
