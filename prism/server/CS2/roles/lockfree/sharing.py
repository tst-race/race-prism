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

from typing import List, Optional, Sequence

from prism.server.CS2.roles.lockfree.preproduct import Triple
from prism.common.crypto.secretsharing import get_ssobj
from prism.common.crypto.modmath import gen_prime
from prism.common.message import Share, SecretSharingMap, PrismMessage
from prism.common.config import configuration


def dummy_handler(f):
    """Decorator that wraps operations that return shares, and ensures that if any of the inputs are missing or dummies,
    a dummy share is returned. Dummy shares have x==-1, and are used to handle missing results."""

    def handle_dummy(self, *args):
        for arg in args:
            if arg is None:
                return self.dummy
            if isinstance(arg, Share) and arg.is_dummy:
                return self.dummy

        return f(self, *args)

    return handle_dummy


class Sharing:
    """A wrapper for a secret sharing system, providing common arithmetic operations."""

    def __init__(self, nparties: int, threshold: int, modulus: int = None):
        if not modulus:
            modulus = gen_prime(configuration.mpc_nbits_modulus)
        self.secret_sharing = get_ssobj(nparties, threshold, modulus)

    @property
    def parameters(self) -> SecretSharingMap:
        return self.secret_sharing.parameters

    @property
    def nparties(self) -> int:
        return self.secret_sharing.nparties

    @property
    def threshold(self) -> int:
        return self.secret_sharing.threshold

    @property
    def modulus(self) -> int:
        return self.secret_sharing.modulus

    @property
    def dummy(self) -> Share:
        """A dummy share. Any operation with a dummy share as input will output another dummy share instead of
        attempting to calculate."""
        return Share(0, x=-1)

    def share(self, secret: int) -> List[Share]:
        return self.secret_sharing.share(secret)

    def open(self, shares: Sequence[Share]) -> Optional[int]:
        """Uses a set of shares to reconstruct the original value. Returns None if not enough shares are available."""
        real_shares = [share for share in shares if share and share.x != -1]
        if len(real_shares) < self.threshold:
            return None
        return self.secret_sharing.reconstruct(real_shares)

    @dummy_handler
    def add(self, a: Optional[Share], b: Optional[Share]) -> Share:
        assert a.x == b.x
        return Share((a.share + b.share) % self.modulus, a.x)

    @dummy_handler
    def addc(self, a: Optional[Share], b: int) -> Share:
        return Share((a.share + b) % self.modulus, a.x)

    @dummy_handler
    def sub(self, a: Optional[Share], b: Optional[Share]) -> Share:
        assert a.x == b.x
        return Share((a.share - b.share) % self.modulus, a.x)

    @dummy_handler
    def subc(self, a: Optional[Share], b: int) -> Share:
        return Share((a.share - b) % self.modulus, a.x)

    @dummy_handler
    def mul(self, a: Optional[Share], b: Optional[Share]) -> Share:
        """Warning: Returns a share of a higher degree than the inputs."""
        assert a.x == b.x
        return Share((a.share * b.share) % self.modulus, a.x)

    @dummy_handler
    def mulc(self, a: Optional[Share], b: int) -> Share:
        return Share((a.share * b) % self.modulus, a.x)

    @dummy_handler
    def mul_ed(self, epsilon: int, delta: int, triple: Triple) -> Share:
        return self.addc(
            self.add(self.add(triple.c, self.mulc(triple.b, epsilon)), self.mulc(triple.a, delta)), epsilon * delta
        )

    @staticmethod
    def from_message(message: PrismMessage) -> Sharing:
        ss_map = message.secret_sharing
        return Sharing(ss_map.parties, ss_map.threshold, ss_map.modulus)
