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

from prism.common.config import configuration
from prism.common.epoch.genesis import GenesisInfo
from prism.common.tracing import trace_context
from prism.server.CS2.roles import ClientRegistration
from prism.server.epoch import EpochState
from prism.server.epoch.epoch import Epoch


class GenesisEpoch(Epoch):
    def __init__(self, server, previous: Epoch, genesis_info: GenesisInfo):
        super().__init__("genesis", server, previous, None)
        self.configuration = configuration

        if "pseudonym" in self.configuration:
            self.pseudonym = bytes.fromhex(self.configuration.pseudonym)

        self.role = self.generate_role()
        self.state = EpochState.RUNNING

        self.genesis_info = genesis_info

    def generate_role(self):
        role_name = self.configuration.get("role", "dummy")
        dropbox_index = self.configuration.get("db_index", None)

        committee = role_name
        if dropbox_index is not None:
            committee += str(dropbox_index)

        role = self.make_role(role_name, committee, dropbox_index, None)
        return role

    async def run(self):
        if isinstance(self.role, ClientRegistration):
            self.role.client.genesis_info = self.genesis_info
        else:
            with trace_context(self.logger, "load-genesis-links") as scope:
                scope.debug("Loading genesis links...")
                await self.load_genesis_links()
                scope.debug("...loaded genesis links.")

        await super().run()

    async def load_genesis_links(self):
        async def load_link(prof):
            lnk = await self.transport.load_profile(prof)
            if not lnk:
                self.logger.warning(f"Failed to load genesis link profile {prof}")
            return lnk

        router = self.role.router
        neighborhood = router.neighborhood

        for neighbor in self.genesis_info.neighbors:
            neighborhood.update(neighbor.name, neighbor.pseudonym, neighbor.public_key,
                                neighbor.control_addresses, neighbor.tag)

        while not self.genesis_info.loaded:
            for profile in self.genesis_info.unloaded_receive_links:
                link = await load_link(profile)
                if link:
                    router.incoming_links.append(link)

            for profile in self.genesis_info.unloaded_broadcast_links:
                link = await load_link(profile)
                if link:
                    router.broadcast_links.append(link)

            for profile in self.genesis_info.unloaded_send_links:
                link = await load_link(profile)
                if link:
                    neighbor_pseudonym = next(neighbor.pseudonym for neighbor in self.genesis_info.neighbors
                                              if neighbor.name in profile.personas)
                    neighbor = neighborhood[neighbor_pseudonym]
                    if not neighbor:
                        continue
                    neighbor.data_links.append(link)
