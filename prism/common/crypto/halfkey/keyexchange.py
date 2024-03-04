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
# TODO - move CBOR stuff into PrismMessage

# CBOR keys
FIELD_KEY_TYPE = 0
FIELD_DH_P = 1
FIELD_DH_G = 2
# Q is currently written to dictionaries but not read from
FIELD_DH_Q = 3
FIELD_DH_Y = 4
FIELD_ECDH_PUBLIC = 5
FIELD_RSA_PUBLIC = 6

# Values for FIELD_KEY_TYPE
KEY_TYPE_DH = 0
KEY_TYPE_ECDH = 1

AES_KEY_LENGTH_BYTES = 32


class PrivateKey:
    def public_key(self) -> PublicKey:
        pass

    def exchange(self, public_key, salt: bytes) -> bytes:
        pass

    def serialize(self) -> bytes:
        pass


class PublicKey:
    def generate_private(self) -> PrivateKey:
        pass

    def cbor(self) -> dict:
        pass


class KeySystem:
    def generate_private(self) -> PrivateKey:
        pass

    @staticmethod
    def load_public(cbor: dict) -> PublicKey:
        key_type = cbor[FIELD_KEY_TYPE]

        if key_type == KEY_TYPE_ECDH:
            from .ecdh import EllipticCurveDiffieHellman
            return EllipticCurveDiffieHellman.load_public(cbor)

    @staticmethod
    def load_private(data: bytes) -> PrivateKey:
        pass
