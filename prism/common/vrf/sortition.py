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
from typing import Tuple

from .octets import bytes2ip
from .distribution import VRFDistribution


try:
    import cryptography
    CRYPTOGRAPHY_AVAILABLE = True
except:
    CRYPTOGRAPHY_AVAILABLE = False


class PrismSortition(Enum):
    STATIC = auto()
    VRF = auto()


class VRFSortition:
    def __init__(self, distribution: VRFDistribution):
        self.rd = distribution

    def sort_and_prove(self, sk, alpha: bytes) -> Tuple[str, str]:
        # SK is a cryptography secret key
        # alpha is type bytes (the payload)
        # pass proof and distribution to a sortition function to get a role
        # output the role and the proof
        from prism.common.vrf.vrf import VRF_prove, serialize_proof, VRF_proof_to_hash
        pi = VRF_prove(sk, alpha)
        serial = serialize_proof(sk.public_key(), alpha, pi)
        h = bytes2ip(VRF_proof_to_hash(pi))
        return self.rd.role(h), serial

    def verify(self, serial_proof: str, role: str) -> bool:
        # TODO - Make this work on Android and remove
        if not CRYPTOGRAPHY_AVAILABLE:
            return True

        # input a serialized proof, claimed role, and a distribution
        from prism.common.vrf.vrf import deserialize_proof, VRF_verify, VRF_proof_to_hash
        pk, alpha, pi = deserialize_proof(serial_proof)
        if VRF_verify(pk, alpha, pi):
            beta = bytes2ip(VRF_proof_to_hash(pi))
            return self.rd.role(beta) == role
        else:
            return False
