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

from prism.common.vrf.distribution import VRFConfig, VRFDistribution
from prism.common.vrf.sortition import VRFSortition
from prism.server.CS2.roles.announcing_role import AnnouncingRole
from prism.server.epoch.epoch import Epoch


class VRFEpoch(Epoch):
    def __init__(self, server, previous: Epoch, seed: str):
        super().__init__(seed, server, previous, None)
        from prism.server.newserver import PrismServer
        server: PrismServer
        self.seed = seed
        self.vrf_config = VRFConfig.from_config(server.configuration)
        distribution, committees = VRFDistribution.role_distribution(self.vrf_config)
        sortition = VRFSortition(distribution)
        self.role = self._sort_into_role(committees, sortition, self.key_material.server_key.private_key)
        if isinstance(self.role, AnnouncingRole):
            self.role.vrf_sortition = sortition

    def _sort_into_role(self, committees, sortition, vrf_key):
        committee, proof = sortition.sort_and_prove(vrf_key, self.seed.encode("utf-8"))

        dropbox_index = None
        if committee == "OFF":
            role_name = "DUMMY"
        elif "DROPBOX" in committee:
            if self.server.configuration.get("vrf_dropbox_ss", False):
                role_name = "DROPBOX"
            else:
                role_name = "DROPBOX_LF"

            n_range, m_replica = committees[committee]
            if self.server.configuration.get("vrf_db_index_from_range_ids", True):
                dropbox_index = n_range - 1
            else:
                dropbox_index = (n_range - 1) * self.vrf_config.m_replicas + (m_replica - 1)
        else:
            role_name = committee

        return self.make_role(role_name, committee, dropbox_index, proof)
