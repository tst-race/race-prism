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
from typing import List

from prism.common.cleartext import ClearText


class MessageStore:
    messages: List[ClearText]

    def __init__(self, configuration):
        self.config = configuration
        self.messages = []

    def record(self, message: ClearText):
        self.messages.append(message)

    def contacts(self):
        return {address
                for message in self.messages
                for address in [message.sender, message.receiver]
                if address != self.config.name}

    def received(self) -> List[ClearText]:
        return [message for message in self.messages if message.receiver == self.config.name]

    def conversations(self) -> dict:
        return {contact: self.conversation_with(contact) for contact in self.contacts()}

    def conversation_with(self, address: str) -> List[ClearText]:
        convo = [message for message in self.messages if message.sender == address or message.receiver == address]
        return sorted(convo, key=lambda m: m.timestamp)

