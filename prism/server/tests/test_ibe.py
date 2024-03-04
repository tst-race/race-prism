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
from prism.common.crypto.ibe import BonehFranklin

ALICE_IDENTITY = "alice@example.com"
BOB_IDENTITY = "bob@example.com"


def msg_check(alice_ibe, bob_ibe):
    test_msg_1 = "Hello Alice"
    encrypted = bob_ibe.encrypt(ALICE_IDENTITY, test_msg_1.encode("utf-8"))
    decrypted_1 = alice_ibe.decrypt(encrypted).decode("utf-8")

    assert decrypted_1 == test_msg_1

    test_msg_2 = "Hello Bob"
    encrypted = alice_ibe.encrypt(BOB_IDENTITY, test_msg_2.encode("utf-8"))
    decrypted_2 = bob_ibe.decrypt(encrypted).decode("utf-8")

    assert decrypted_2 == test_msg_2


def test_ibe():
    generator = BonehFranklin.generate(3)
    param_str = generator.public_params

    alice_key = generator.generate_private_key(ALICE_IDENTITY)
    bob_key = generator.generate_private_key(BOB_IDENTITY)

    alice_ibe = BonehFranklin.load(ALICE_IDENTITY, private_key=alice_key, public_params=param_str)
    bob_ibe = BonehFranklin.load(BOB_IDENTITY, private_key=bob_key, public_params=param_str)

    msg_check(alice_ibe, bob_ibe)


def test_load_generator():
    g1 = BonehFranklin.generate(3)
    param_str = g1.public_params
    secret_str = g1.system_secret

    g2 = BonehFranklin.load_generator(param_str, secret_str)
    assert g1.public_params == g2.public_params
    assert g1.system_secret == g2.system_secret

    alice_key = g1.generate_private_key(ALICE_IDENTITY)
    bob_key = g2.generate_private_key(BOB_IDENTITY)

    alice_ibe = BonehFranklin.load(ALICE_IDENTITY, private_key=alice_key, public_params=param_str)
    bob_ibe = BonehFranklin.load(BOB_IDENTITY, private_key=bob_key, public_params=param_str)

    msg_check(alice_ibe, bob_ibe)
