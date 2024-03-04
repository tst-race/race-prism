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
from typing import Union, List

from prism.common.crypto.secretsharing.secretsharing import SecretSharing
from prism.common.message import SecretSharingMap, SecretSharingType, Share


class FullThresholdSS(SecretSharing):

    def __init__(self, nparties: int, modulus: int):
        super(FullThresholdSS, self).__init__(
            SecretSharingMap(sharing_type=SecretSharingType.FULL,
                             parties=nparties, threshold=nparties, modulus=modulus))

    def share(self, value: Union[int, Share], coeff_required: bool = False) -> List[Share]:
        if isinstance(value, Share):
            value = value.share
        shares = []
        addedsum = 0
        for i in range(self.nparties - 1):
            ishare = random.randrange(1, self.modulus)
            addedsum += ishare
            shares.append(Share(ishare, i))
        shares.append(Share((value - addedsum) % self.modulus, self.nparties - 1))
        return shares

    def reconstruct(self, shares: List[Share], iq: int = 0, mode: int = 0) -> int:
        value = 0
        for share in shares:
            value += share.share
        return value % self.modulus

    def random_polynomial_root_at(self, iq: int) -> List[Share]:
        pass

    def commit(self, value: int) -> int:
        pass
