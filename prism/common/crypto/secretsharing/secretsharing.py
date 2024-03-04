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

#####
# Title: Interface for Secret Sharing
# Author: Sashidhar Jakkamsetti
# Email: sjakkams@uci.edu
# Company: SRI and University of California Irvine
####
import math
from abc import ABCMeta, abstractmethod
from typing import List, Union

import cbor2

from prism.common.message import SecretSharingMap, Share


class SecretSharing(metaclass=ABCMeta):
    def __init__(self, ssparams: SecretSharingMap):
        assert ssparams
        assert ssparams.parties >= 3
        self._parameters = ssparams

    def __str__(self):
        return f'{self.__class__.__name__} with nparties={self.nparties} and threshold={self.threshold}'

    @property
    def parameters(self) -> SecretSharingMap:
        return self._parameters

    @property
    def nparties(self) -> int:
        return self._parameters.parties

    @property
    def threshold(self) -> int:
        return self._parameters.threshold

    @property
    def modulus(self) -> int:
        return self._parameters.modulus

    @property
    def p(self):
        return self._parameters.p

    @property
    def g(self):
        return self._parameters.g

    @abstractmethod
    def share(self, value: Union[int, Share], coeff_required: bool = False) -> List[Share]:
        pass

    @abstractmethod
    def reconstruct(self, shares: List[Share], iq: int = 0, mode: int = 0) -> int:
        pass

    @property
    def chunk_size_bytes(self) -> int:
        """The carrying capacity of a single share when splitting a secret into chunks."""
        max_bits = self.modulus.bit_length() - 1
        max_bytes = int(max_bits / 8)
        return max_bytes - 2

    def encode_chunk(self, data: bytes) -> int:
        result = int.from_bytes(cbor2.dumps(data), byteorder="big", signed=False)
        assert result < self.modulus
        return result

    def decode_chunk(self, secret: int) -> bytes:
        assert secret < self.modulus
        return cbor2.loads(secret.to_bytes(math.ceil(secret.bit_length() / 8), "big", signed=False))

    def encode_bytes(self, data: bytes) -> List[int]:
        return [self.encode_chunk(data[i:i+self.chunk_size_bytes]) for i in range(0, len(data), self.chunk_size_bytes)]

    def decode_bytes(self, secrets: List[int]) -> bytes:
        return b''.join(self.decode_chunk(s) for s in secrets)

    def share_bytes(self, data: bytes, coeff_required: bool = False) -> List[List[Share]]:
        """Secret shares some bytes, and returns a list of lists of shares.
        The outer list is indexed by party, the inner lists are one or more shares, depending on the
        length of the original data."""
        chunks = [self.share(secret, coeff_required=coeff_required) for secret in self.encode_bytes(data)]
        return [list(batch) for batch in zip(*chunks)]

    def reconstruct_bytes(self, shares: List[List[Share]], iq: int = 0, mode: int = 0) -> bytes:
        """Reconstruct original bytes from list of lists of shares created by share_bytes."""
        chunks = [list(batch) for batch in zip(*shares)]
        secrets = [self.reconstruct(chunk, iq=iq, mode=mode) for chunk in chunks]
        return self.decode_bytes(secrets)

    def join_shares(self, shares: List[Share]) -> bytes:
        """Packs a series of shares into a byte array."""
        return cbor2.dumps([shares[0].x, *[share.share for share in shares]])

    def split_shares(self, data: bytes) -> List[Share]:
        """Reconstructs share objects from a bytes created by join_shares."""
        arr = cbor2.loads(data)
        return [Share(share, x=arr[0]) for share in arr[1:]]

    def random_polynomial_root_at(self, iq: int) -> List[Share]:
        raise NotImplementedError

    def commit(self, value: int) -> int:
        raise NotImplementedError

    def verify(self, share: Share) -> bool:
        return True

    def verifyd(self, share: int, x: int, coeffcommits: List) -> bool:
        return True

    def verify_doubleshares(self, shares) -> bool:
        return True
