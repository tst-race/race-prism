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
import random
from typing import List, Union

from prism.common.crypto.secretsharing.secretsharing import SecretSharing
from prism.common.message import SecretSharingMap, SecretSharingType, Share
from prism.common.crypto.modmath import modinv


class ShamirSS(SecretSharing):

    def __init__(self, nparties: int, threshold: int, modulus: int):
        super(ShamirSS, self).__init__(
            SecretSharingMap(sharing_type=SecretSharingType.SHAMIR,
                             parties=nparties, threshold=threshold, modulus=modulus))

    def _P(self, coeffs: List[int], x) -> int:
        y = 0
        for i, coeff in enumerate(coeffs):
            y = (y + (coeff * (x ** i))) % self.modulus
        return y

    def share(self, value: Union[int, Share], coeff_required: bool = False) -> List[Share]:
        if isinstance(value, Share):
            coeffs = [value.share]
        else:
            coeffs = [value]
        for i in range(1, self.threshold):
            coeffs.append(random.randrange(1, self.modulus))
        return [Share(self._P(coeffs, i + 1), i) for i in range(self.nparties)]

    def _recoverCoefficients(self, x_points: List[int], ir: int) -> List[int]:
        coeffs = []
        for i in x_points:
            result = 1
            for j in x_points:
                if i != j:
                    result = (result * (ir - j) * modinv((i - j), self.modulus)) % self.modulus
            coeffs.append(int(result))
        return coeffs

    def reconstruct(self, shares: List[Share], iq: int = 0, mode: int = 0) -> int:
        x_points = [s.x + 1 for s in shares]  # points on X axis start from 1, not from 0 (like the peer indices)
        coeff = self._recoverCoefficients(x_points, iq)
        value = 0
        for i in range(len(shares)):
            value = (value + (coeff[i] * shares[i].share)) % self.modulus
        return value

    def random_polynomial_root_at(self, iq: int) -> List[Share]:
        init_coeff = [random.randrange(1, self.modulus) for _ in range(self.threshold - 1)]
        init_coeff.append(0)
        coeff = [init_coeff[0]]
        for i in range(1, self.threshold):
            coeff.insert(0, (init_coeff[i] - (iq * init_coeff[i - 1])) % self.modulus)
        return [Share(self._P(coeff, i + 1), i) for i in range(self.nparties)]

    def commit(self, value: int) -> int:
        pass