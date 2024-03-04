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
from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import HKDF
from Crypto.PublicKey import RSA, ECC
from Crypto.PublicKey.ECC import EccKey

import pytest
from typing import *

from prism.common.crypto.halfkey import EllipticCurveDiffieHellman
from prism.common.crypto.halfkey.keyexchange import KeySystem
from prism.common.crypto.ibe import IdentityBasedEncryption
from prism.common.crypto.util import make_aes_key, make_nonce
from prism.common.message import PrismMessage, TypeEnum
from prism.common.message_utils import encrypt_user_message, decrypt_user_message

CURVE_NAME = 'ed25519'


class TestIBE(IdentityBasedEncryption):
    def encrypt_raw(self, address: str, plaintext: bytes) -> bytes:
        return plaintext

    def decrypt_raw(self, ciphertext: bytes) -> Optional[bytes]:
        return ciphertext


def test_aes_gcm():
    HexMyKey = '6f9b706748f616fb0cf39d274638ee29813dbad675dd3d976e80bde4ccd7546a'
    HexEncryptedOriginalMessage = '6b855acc799213c987a0e3fc4ddfb7719c9b87fcf0a0d35e2e781609143b6e2d8e743cf4aea728002a9fc77ef834'
    key = bytes.fromhex(HexMyKey)
    data = bytes.fromhex(HexEncryptedOriginalMessage)
    cipher = AES.new(key, AES.MODE_GCM, data[:16])  # nonce
    dec = cipher.decrypt_and_verify(data[16:-16], data[-16:])  # ciphertext, tag
    assert dec == b'my secret data'


def test_ibe_aes():
    data = b"secret"
    key = make_aes_key()
    nonce = make_nonce()

    alice_cipher = AES.new(key, AES.MODE_GCM, nonce)
    ciphertext, tag = alice_cipher.encrypt_and_digest(data)

    bob_cipher = AES.new(key, AES.MODE_GCM, nonce)
    plaintext = bob_cipher.decrypt_and_verify(ciphertext, tag)

    assert plaintext == data


def test_ibe():
    alice_ibe = TestIBE("alice")
    addr = "address"
    plaintext = b"plaintext"
    encrypted = alice_ibe.encrypt(addr, plaintext)

    bob_ibe = TestIBE("bob")
    decrypted = bob_ibe.decrypt(encrypted)
    assert decrypted == plaintext


@pytest.fixture
def pm():
    return PrismMessage(
        msg_type=TypeEnum.USER_MESSAGE,
        name="Alice",
        messagetext="super secret message",
    )


def test_user_msg(pm):
    alice_ibe = TestIBE("alice")
    pm_encrypted = encrypt_user_message(alice_ibe, "bob", pm)

    bob_ibe = TestIBE("bob")
    pm_decrypted = decrypt_user_message(bob_ibe, pm_encrypted)
    assert pm_decrypted.name == pm.name
    assert pm_decrypted.messagetext == pm.messagetext


def test_rsa():
    private_key = RSA.generate(2048)
    public_key = private_key.publickey()
    cipher_rsa = PKCS1_OAEP.new(public_key)
    ciphertext = cipher_rsa.encrypt(b'secret message')

    cipher_receiver = PKCS1_OAEP.new(private_key)
    decrypted = cipher_receiver.decrypt(ciphertext)

    assert decrypted == b'secret message'


def test_ecc():
    data = b"secret message"
    nonce = make_nonce()

    alice_key = EllipticCurveDiffieHellman().generate_private()
    bob_key = EllipticCurveDiffieHellman().generate_private()
    # from Alice's perspective, load the peer key from Bob's public key
    bob_public_as_cbor = bob_key.public_key().cbor()
    peer_bob_key = KeySystem.load_public(bob_public_as_cbor)
    alice_shared_key = alice_key.exchange(peer_bob_key, b'')
    aes_alice = AES.new(alice_shared_key, AES.MODE_GCM, nonce)
    ciphertext = aes_alice.encrypt(data)

    # from Bob's perspective, load the peer key from Alice's public key
    alice_public_as_cbor = alice_key.public_key().cbor()
    peer_alice_key = KeySystem.load_public(alice_public_as_cbor)
    bob_shared_key = bob_key.exchange(peer_alice_key, b'')
    aes_bob = AES.new(bob_shared_key, AES.MODE_GCM, nonce)
    plaintext = aes_bob.decrypt(ciphertext)

    assert plaintext == data


# @pytest.mark.skip(reason="This is currently generating an OverflowError because multiplying integers too big")
def test_ecdh_exchange():
    data = b"secret"
    nonce = make_nonce()

    alicePrivKey = ECC.generate(curve=CURVE_NAME)
    alicePubKey = alicePrivKey.public_key()
    print("\nAlice public key:", alicePubKey.export_key(format='raw').hex())

    bobPrivKey = ECC.generate(curve=CURVE_NAME)
    bobPubKey = bobPrivKey.public_key()
    print("Bob public key:", bobPubKey.export_key(format='raw').hex())

    # print("Now exchange the public keys (e.g. through Internet)")

    aliceSharedKey = bobPubKey.pointQ * alicePrivKey.d
    print("Alice shared key:", str(aliceSharedKey.x).encode())

    bobSharedKey = alicePubKey.pointQ * bobPrivKey.d
    print("Bob shared key:", str(bobSharedKey.x).encode())

    print("Equal shared keys:", aliceSharedKey == bobSharedKey)

    alice_key = HKDF(master=str(aliceSharedKey.x).encode(),
                     key_len=32,
                     salt=b'',
                     hashmod=SHA256,
                     context=b'prism halfkey')
    alice_aes = AES.new(alice_key, AES.MODE_GCM, nonce)
    ciphertext = alice_aes.encrypt(data)

    bob_key = HKDF(master=str(bobSharedKey.x).encode(),
                   key_len=32,
                   salt=b'',
                   hashmod=SHA256,
                   context=b'prism halfkey')
    bob_aes = AES.new(bob_key, AES.MODE_GCM, nonce)
    plaintext = bob_aes.decrypt(ciphertext)

    assert data == plaintext


def test_ecc_loading():
    alice_key = EllipticCurveDiffieHellman().generate_private()
    alice_serialized = alice_key.serialize()
    alice_loaded = EllipticCurveDiffieHellman.load_private(alice_serialized)
    assert alice_key == alice_loaded

    alice_public = alice_key.public_key()
    loaded_public = KeySystem.load_public(alice_public.cbor())
    assert alice_public == loaded_public
