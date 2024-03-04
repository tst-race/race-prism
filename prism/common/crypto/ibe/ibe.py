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
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from typing import Optional
from Crypto.Cipher import AES

from prism.common.crypto.util import make_aes_key, make_nonce


@dataclass
class EncryptedMessage:
    ciphertext: bytes
    key: bytes
    nonce: bytes


class DecryptException(BaseException):
    pass


class IdentityBasedEncryption(metaclass=ABCMeta):
    identity: str

    def __init__(self, identity: str):
        self.identity = identity

    def encrypt(self, address: str, plaintext: bytes) -> EncryptedMessage:
        key = make_aes_key()
        nonce = make_nonce()
        cipher = AES.new(key, AES.MODE_GCM, nonce)
        ciphertext = cipher.encrypt(plaintext)
        encoded_key = self.encrypt_raw(address, key)
        encrypted = EncryptedMessage(ciphertext, encoded_key, nonce)

        return encrypted

    def decrypt(self, message: EncryptedMessage) -> bytes:
        key = self.decrypt_raw(message.key)
        try:
            cipher = AES.new(key, AES.MODE_GCM, message.nonce)
            return cipher.decrypt(message.ciphertext)
        except (ValueError, KeyError):
            raise DecryptException

    @abstractmethod
    def encrypt_raw(self, address: str, plaintext: bytes) -> bytes:
        pass

    @abstractmethod
    def decrypt_raw(self, ciphertext: bytes) -> Optional[bytes]:
        pass

