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
from dataclasses import dataclass
from typing import Optional

from jaeger_client import SpanContext

from prism.common.message import Share


@dataclass
class Fragment:
    fragment_id: bytes
    pseudonym_share: Share
    ciphertext: bytes
    store_context: Optional[SpanContext]

    def __repr__(self) -> str:
        trace = self.store_context and hex(self.store_context.trace_id)[2:]
        return f"Fragment({self.fragment_id.hex()[:6]}, tr: {trace})"

    def json(self) -> dict:
        j = {
            "id": self.fragment_id.hex(),
            "share": self.pseudonym_share.encode().hex(),
            "ciphertext": self.ciphertext.hex(),
        }

        if self.store_context:
            j["store_trace"] = self.store_context.trace_id
            j["store_span"] = self.store_context.span_id
            j["store_flags"] = self.store_context.flags

        return j

    @classmethod
    def from_json(cls, j: dict) -> Fragment:
        fragment_id = bytes.fromhex(j["id"])
        share = Share.decode(bytes.fromhex(j["share"]))
        ciphertext = bytes.fromhex(j["ciphertext"])

        if "store_trace" in j:
            context = SpanContext(j["store_trace"], j["store_span"], None, j["store_flags"])
        else:
            context = None

        return Fragment(fragment_id, share, ciphertext, context)

    @staticmethod
    def dummy() -> Fragment:
        return Fragment(b"", Share(0, -1), b"", None)
