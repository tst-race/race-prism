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
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from hypercorn.config import Config
from hypercorn.trio import serve
from pydantic import BaseModel

from prism.client.client import PrismClient
from prism.common.cleartext import ClearText

app = FastAPI()

static_path = Path(__file__).parent / "static"
index_path = static_path / "index.html"
app.mount("/assets", StaticFiles(directory=static_path / "assets"), name="assets")

origins = ["*"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

prism_client: PrismClient


async def run_api(client: PrismClient):
    global prism_client
    prism_client = client

    config = Config()
    config.bind = [f"0.0.0.0:{client.config.client_rest_port}"]

    # noinspection PyTypeChecker
    await serve(app, config)


def find_since(msgs: List[ClearText], nonce: Optional[str]) -> List[dict]:
    if not nonce:
        return [m.json() for m in msgs]

    result = []
    found = False

    for msg in msgs:
        if found:
            result.append(msg.json())
        elif msg.nonce_string == nonce:
            found = True

    return result


@app.middleware("http")
async def client_required(request: Request, call_next):
    if prism_client is None:
        raise HTTPException(status_code=503, detail="Server not ready yet.")

    return await call_next(request)


@app.get("/messages")
def messages(since: Optional[str] = None) -> List[dict]:
    return find_since(prism_client.message_store.messages, since)


@app.get("/messages/received")
def received(since: Optional[str] = None) -> List[dict]:
    return find_since(prism_client.message_store.received(), since)


@app.get("/contacts")
def contacts() -> List[str]:
    initial_contacts = set(prism_client.config.get("contacts", []))
    return sorted(list(initial_contacts.union(prism_client.message_store.contacts())))


@app.get("/persona")
def persona() -> str:
    return prism_client.config.name


class MessageSend(BaseModel):
    address: str
    message: str


@app.post("/send")
def send_message(message: MessageSend) -> bool:
    clear = ClearText(receiver=message.address, sender=prism_client.config.name, message=message.message)
    prism_client.process_clear_text(clear)

    return True


@app.get("/conversations/{_contact}", response_class=FileResponse)
def conversations(_contact: str):
    return index_path


@app.get("/", response_class=FileResponse)
def index():
    return index_path
