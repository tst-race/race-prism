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
from prism.common.transport.transport import MessageHook, Package
from prism.common.message import ActionEnum, TypeEnum


class MPCResponseHook(MessageHook):
    op_id: bytes
    op_action: ActionEnum

    def __init__(self, pseudonym: bytes, party_id: int, op_id: bytes, op_action: ActionEnum = None):
        super().__init__()
        self.pseudonym = pseudonym
        self.party_id = party_id
        self.op_id = op_id
        self.op_action = op_action

    def match(self, package: Package) -> bool:
        message = package.message

        if message.msg_type != TypeEnum.MPC_RESPONSE:
            return False

        if message.pseudonym and message.pseudonym != self.pseudonym:
            return False

        if message.dest_party_id != self.party_id:
            return False

        if not message.mpc_map or message.mpc_map.request_id != self.op_id:
            return False

        if self.op_action and message.mpc_map.action != self.op_action:
            return False

        return True
