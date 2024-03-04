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

import httpx
import trio

from prism.common.cleartext import ClearText


class RemoteClient:
    messages: List[ClearText]

    def __init__(self, name: str, host: str, port: int):
        self.name = name
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"

        self.messages = []
        self.running = False
        self.msg_stream_in, self.msg_stream_out = trio.open_memory_channel(0)

    def to_json(self) -> dict:
        return {"name": self.name, "host": self.host, "port": self.port}

    @property
    def last_seen_nonce(self):
        if not self.messages:
            return None

        return self.messages[-1].nonce_string

    async def get_message(self) -> ClearText:
        return await self.msg_stream_out.receive()

    async def send_message(self, message: ClearText):
        async with httpx.AsyncClient() as client:
            while True:
                try:
                    await client.post(f"{self.base_url}/send", json={"address": message.receiver, "message": message.message})
                    break
                except:
                    pass
                await trio.sleep(1.0)

    def quit(self):
        self.running = False

    async def listen(self):
        self.running = True

        async with httpx.AsyncClient() as client:
            while self.running:
                try:
                    await self.check(client)
                except httpx.RemoteProtocolError:
                    pass
                await trio.sleep(0.5)

    async def check(self, client):
        received_url = f"{self.base_url}/messages/received"
        if self.last_seen_nonce:
            params = {"since": self.last_seen_nonce}
        else:
            params = {}
        messages = await client.get(received_url, params=params)
        clears = [ClearText.from_json(j) for j in messages.json()]
        self.messages.extend(clears)

        for clear in clears:
            await self.msg_stream_in.send(clear)
