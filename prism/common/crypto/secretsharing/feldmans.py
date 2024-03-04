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
from prism.common.crypto.secretsharing.berlekampwelch.finitefield import FiniteField
from prism.common.crypto.secretsharing.berlekampwelch.welchberlekamp import makeEncoderDecoder
from prism.common.crypto.modmath import modinv


class FeldmansVSS(SecretSharing):

    def __init__(self, nparties, threshold, modulus, p, g):
        super(FeldmansVSS, self).__init__(
            SecretSharingMap(sharing_type=SecretSharingType.FELDMAN,
                             parties=nparties, threshold=threshold, modulus=modulus, p=p, g=g))
        if threshold - 1 >= nparties/3:
            raise ValueError("threshold - 1 should be less than nparties/3")
        self.enc, self.dec, _ = makeEncoderDecoder(nparties, threshold, modulus)

    def commit(self, value):
        return pow(self.g, value, self.p)

    def verify(self, share: Share) -> bool:
        ref = 1
        for i, cc in enumerate(share.coeffcommits):
            ref = (ref * pow(cc, ((share.x + 1) ** i))) % self.p
        return ref == self.commit(share.share)

    def verifyd(self, share: int, x: int, coeffcommits: List) -> bool:
        ref = 1
        for i, cc in enumerate(coeffcommits):
            ref = (ref * pow(cc, ((x + 1) ** i))) % self.p
        return ref == self.commit(share)

    def _P(self, coeffs, x):
        y = 0
        for i, coeff in enumerate(coeffs):
            y = (y + (coeff * (x ** i))) % self.modulus
        return y

    def share(self, value: Union[int, Share], coeff_required: bool = True) -> List[Share]:
        if isinstance(value, Share):
            coeffs = [value.share]
        else:
            coeffs = [value]
        for i in range(1, self.threshold):
            coeffs.append(random.randrange(1, self.modulus))
        commitcoeffs = [self.commit(c) for c in coeffs]
        return [Share(self._P(coeffs, i + 1), i,
                      commitcoeffs if coeff_required else None,
                      value.originalcommit if isinstance(value, Share) else commitcoeffs[0])
                for i in range(self.nparties)]

    def reconstruct(self, shares: List[Share], iq: int = 0, mode: int = 0) -> int:
        x_points = []
        y_points = []
        if iq == 0:
            x_points = [(share.x + 1) for share in shares]
            y_points = [share.share for share in shares]
        else:
            j = 0
            for i in range(len(shares) + 1):
                if i + 1 != iq:
                    x_points.append(i + 1)
                    y_points.append(shares[j].share)
                    j += 1
                elif mode == 0:
                    x_points.append(i + 1)
                    y_points.append(1)

        # Berlekamp-Welch Interpolation
        if mode == 0:
            try:
                coeff = self._recoverBWCoefficients(x_points, y_points)
                return self._P(coeff, iq)
            except Exception as e:
                if iq <= 0:
                    raise RuntimeError(f"Error during Berlekamp-Welch interpolation: {e}")
                # "Using Lagrange Interpolation instead for recovering."
                mode = 1

        # Lagrange Interpolation (also fallback from above)
        if mode == 1:
            coeff = self._recoverLagrangeCoefficients(x_points, iq)
            value = 0
            for i in range(len(shares)):
                value = (value + (coeff[i] * shares[i].share)) % self.modulus
            return value

    def _recoverBWCoefficients(self, x_points, y_points):
        Fp = FiniteField(self.modulus)
        em = [[Fp(a), Fp(b)] for a, b in zip(x_points, y_points)]
        coeff = self.dec(em)
        return [c.n for c in coeff]

    def _recoverLagrangeCoefficients(self, x_points, ir):
        coeffs = []
        for i in x_points:
            result = 1
            for j in x_points:
                if i != j:
                    result = (result * (ir - j) * modinv((i - j), self.modulus)) % self.modulus
            coeffs.append(int(result))
        return coeffs

    def _recoverDoubleShareLagrangeCoefficients(self, x_points):
        coeffs = []
        for i in x_points:
            result = 1
            for j in x_points:
                if i != j:
                    result = (result * j * modinv((j - i), self.modulus)) % self.modulus
            coeffs.append(int(result))
        return coeffs

    # TODO: Requires Original Coefficient
    def verify_doubleshares(self, shares):
        x_points = [(i + 1) for i in range(len(shares))]
        coeff = self._recoverDoubleShareLagrangeCoefficients(x_points)
        testcommit = 1
        for i, share in enumerate(shares):
            testcommit = (testcommit * pow(share.coeffcommits[0], coeff[i], self.p)) % self.p
        return testcommit == shares[0].originalcommit

    def random_polynomial_root_at(self, iq: int) -> List[Share]:
        init_coeff = [random.randrange(1, self.modulus) for _ in range(self.threshold - 1)]
        init_coeff.append(0)
        coeffs = [init_coeff[0]]
        for i in range(1, self.threshold):
            coeffs.insert(0, (init_coeff[i] - (iq * init_coeff[i - 1])) % self.modulus)
        commitcoeffs = [self.commit(c) for c in coeffs]
        return [Share(self._P(coeffs, i + 1), i, commitcoeffs) for i in range(self.nparties)]