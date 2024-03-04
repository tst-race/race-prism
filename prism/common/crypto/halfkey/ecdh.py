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

from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import HKDF
from Crypto.PublicKey import ECC
from Crypto.PublicKey.ECC import EccKey
from typing import Dict, List

from .keyexchange import *

CURVE_NAME = 'ed25519'


class EllipticCurveDiffieHellman(KeySystem):
    def generate_private(self) -> PrivateKey:
        return ECDHPrivateKey()

    @staticmethod
    def load_private(data: bytes) -> PrivateKey:
        key = ECC.import_key(data)
        return ECDHPrivateKey(key)

    @staticmethod
    def load_public(cbor: dict) -> PublicKey:
        assert cbor[FIELD_KEY_TYPE] == KEY_TYPE_ECDH
        data = cbor[FIELD_ECDH_PUBLIC]
        return ECDHPublicKey(ECC.import_key(data))


class ECDHPublicKey(PublicKey):
    def __init__(self, public_key: EccKey):
        self.public_key = public_key

    def __eq__(self, other):
        if not isinstance(other, ECDHPublicKey):
            return False
        return self.public_key == other.public_key

    def generate_private(self) -> PrivateKey:
        return ECDHPrivateKey()

    def cbor(self) -> dict:
        return {
            FIELD_KEY_TYPE: KEY_TYPE_ECDH,
            FIELD_ECDH_PUBLIC: self.serialize()
        }

    def serialize(self) -> bytes:
        return self.public_key.export_key(format='PEM').encode()

    def __str__(self):
        return f"ECDHPublicKey({self.serialize().hex()})"


class ECDHPrivateKey(PrivateKey):
    def __init__(self, private_key: EccKey = None):
        if private_key:
            self.private_key: EccKey = private_key
        else:
            self.private_key: EccKey = ECC.generate(curve=CURVE_NAME)

    def __eq__(self, other):
        if not isinstance(other, ECDHPrivateKey):
            return False
        return self.private_key == other.private_key

    def public_key(self) -> ECDHPublicKey:
        return ECDHPublicKey(self.private_key.public_key())

    def exchange(self, public_key: ECDHPublicKey, salt: bytes = b'') -> bytes:
        secret = public_key.public_key.pointQ * self.private_key.d
        return HKDF(master=str(secret.x).encode(),
                    key_len=AES_KEY_LENGTH_BYTES,
                    salt=salt,
                    hashmod=SHA256,
                    context=b'prism halfkey')

    def serialize(self) -> bytes:
        return self.private_key.export_key(format='PEM').encode()

    def __str__(self):
        return f"ECDHPrivateKey({self.serialize().hex()})"


def public_dict_from_list(l: List) -> Dict:
    if len(l) != 1:
        raise ValueError("need exactly 1 item to create public dict")
    return {FIELD_KEY_TYPE: KEY_TYPE_ECDH, FIELD_ECDH_PUBLIC: l[0]}
