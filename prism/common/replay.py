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
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Optional

from cbor2 import CBORDecodeError

from prism.common.transport.transport import Link
from prism.common.message import PrismMessage, TypeEnum


def hexdigest(data: bytes) -> str:
    sha = hashlib.sha256()
    sha.update(data)
    return sha.hexdigest()


class Replay:
    def __init__(self, sender, log_path, checksum_bytes=0):
        if log_path:
            self.log_path = Path(log_path)
        else:
            self.log_path = None
        self.sender = sender
        self.file = None
        self.receive_file = None
        self.start_time = None
        self.checksum_bytes = checksum_bytes

    def start(self):
        if self.file:
            self.stop()

        if not self.log_path:
            return

        self.file = open(self.log_path.joinpath("replay.log"), "w")
        self.receive_file = open(self.log_path.joinpath("receive.log"), "w")
        self.start_time = datetime.today()

    def stop(self):
        if not self.log_path:
            return

        self.file.close()
        self.file = None
        self.receive_file.close()
        self.receive_file = None

    def log_receive(self, links: List[Link], data: bytes, trace):
        if not self.log_path:
            return

        recvtime = (datetime.today() - self.start_time) / timedelta(microseconds=1)

        if len(links) != 1:
            transmission_type = "unknown"
            sender = "unknown"
        else:
            link = links[0]
            transmission_type = str(link.channel.transmission_type).lower()
            sender = list(link.endpoints)[0]

        entry = {
            "sender": sender,
            "receiver": self.sender,
            "size": len(data),
            "transmissiontype": transmission_type,
            "recvtime": recvtime,
            "tags": self._create_tags(hexdigest(data), links, data, trace),
        }
        json.dump(entry, self.receive_file)
        self.receive_file.write("\n")
        self.receive_file.flush()

    def log(self, receiver, link: Link, data: bytes, trace: int, handle: Optional[int]):
        if not self.log_path:
            return

        sendtime = (datetime.today() - self.start_time) / timedelta(microseconds=1)

        transmission_type = str(link.channel.transmission_type).lower()

        entry = {
            "sender": self.sender,
            "receiver": receiver,
            "size": len(data),
            "transmissiontype": transmission_type,
            "senttime": sendtime,
            "tags": self._create_tags(hexdigest(data), [link], data, trace, handle=handle),
        }
        json.dump(entry, self.file)
        self.file.write("\n")
        self.file.flush()

    def _create_tags(self, hexdigest: str, links: List[Link], data: bytes, trace, handle: int = None) -> Dict:
        tags = {
            "hash": hexdigest,
            "time": datetime.now(timezone.utc).isoformat(),
            "links": [link.link_id for link in links],
        }
        if trace:
            tags["trace"] = hex(trace).replace("0x", "")
        if handle is not None:
            tags["handle"] = handle
        try:
            cipher_text = bytes(data)
            message_data = cipher_text[self.checksum_bytes:]
            prism_message = PrismMessage.decode(message_data)
            tags["prism_type"] = str(prism_message.msg_type)
            tags["prism_digest"] = prism_message.hexdigest()
            if prism_message.sub_msg:
                tags["submessage"] = TypeEnum(prism_message.sub_msg.msg_type).name
            if prism_message.mpc_map:
                tags["mpc_action"] = str(prism_message.mpc_map.action)
        except (CBORDecodeError, Exception) as e:
            tags["prism_type"] = f"<Error: {e}>"
        return tags
