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
import itertools

from prism.common.crypto.halfkey import EllipticCurveDiffieHellman
from prism.server.CS2.roles import ClientRegistration
from prism.server.epoch import Epoch, EpochState


class SavedEpoch(Epoch):
    def __init__(self, server, saved_state: dict):
        self.__class__.serial_num_iterator = itertools.count(saved_state["serial_number"])
        private_key = EllipticCurveDiffieHellman.load_private(bytes.fromhex(saved_state["private_key"]))
        super().__init__(saved_state["name"], server, None, private_key)
        self.logger.debug(f"Loading saved epoch with state: {saved_state}")
        self.state = EpochState.RUNNING
        self.pseudonym = bytes.fromhex(saved_state["pseudonym"])
        self.role = self.load_role(saved_state)

    def load_role(self, saved_state):
        role_name = saved_state["role_name"]
        committee = saved_state["committee"]
        dropbox_index = saved_state["dropbox_index"]
        proof = saved_state.get("proof")
        return self.make_role(role_name, committee, dropbox_index, proof)

    async def run(self):
        if not isinstance(self.role, ClientRegistration):
            await self.role.router.load_state()

        await super().run()
