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
from cbor2 import CBORDecodeError
from Crypto.Cipher import AES
import structlog
from typing import *

from prism.common.crypto.halfkey.keyexchange import PrivateKey, PublicKey, KeySystem
from prism.common.message import PrismMessage

LOGGER = structlog.getLogger(__name__)


def decrypt(encrypted_msg: PrismMessage, private_key: PrivateKey, pub_key: PublicKey = None) -> Optional[PrismMessage]:
    plaintext = decrypt_data(encrypted_msg, private_key=private_key, pub_key=pub_key)
    if plaintext is not None:
        try:
            return PrismMessage.decode(plaintext)
        except Exception as e:
            import traceback
            LOGGER.error(f"Encountered exception {e} when decoding message.")
            LOGGER.error(f"Message plaintext: {plaintext.hex()}")
            LOGGER.error(f"Traceback: {traceback.format_exc()}")

    return None


def decrypt_data(encrypted_msg: PrismMessage, private_key: PrivateKey, pub_key: PublicKey = None) -> Optional[bytes]:
    if encrypted_msg.half_key:
        pub_key = KeySystem.load_public(encrypted_msg.half_key.as_cbor_dict())

    if pub_key and encrypted_msg.ciphertext and encrypted_msg.nonce:
        try:
            key = private_key.exchange(pub_key, b'')
            aes = AES.new(key, AES.MODE_GCM, encrypted_msg.nonce)
            return aes.decrypt(encrypted_msg.ciphertext)
        except (ValueError, KeyError):
            # fall through to logging
            pass
    LOGGER.warning(f'Cannot decrypt {encrypted_msg}')
    return None


def encrypt(message: PrismMessage, private_key: PrivateKey, peer_key: PublicKey, nonce: bytes) -> bytes:
    return encrypt_data(message.encode(), private_key, peer_key, nonce)


def encrypt_data(plaintext: bytes, private_key: PrivateKey, peer_key: PublicKey, nonce: bytes) -> bytes:
    key = private_key.exchange(peer_key, b'')
    aes = AES.new(key, AES.MODE_GCM, nonce)
    return aes.encrypt(plaintext)
