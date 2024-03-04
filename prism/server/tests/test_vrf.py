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
import pytest
import random

from prism.common.vrf.vrf import sha_hash, MGF1, mod_exp, VRF_keyGen, RSASP1, RSAVP1, VRF_prove, VRF_verify, serialize_proof, \
    deserialize_proof
from prism.common.vrf.octets import bytes2ip, i2bytes
from prism.common.vrf.distribution import VRFDistribution
from prism.common.vrf.sortition import VRFSortition


def test_bytes2ip():
    x = b'hello world'
    assert bytes2ip(x) == bytes2ip(i2bytes(bytes2ip(x), 64))


# test the sha output length
def test_shalen():
    sha = sha_hash(b'\x01\x00\x01')
    assert len(sha) == 32
    sha2 = sha_hash(b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')
    assert len(sha2) == 32


def test_MFG1():
    assert len(MGF1(b'\x01\x01\x01', 32)) == 32
    assert len(MGF1(b'\x01\x01\x01', 63)) == 63
    assert len(MGF1(b'\x01\x01\x01', 0)) == 0


def test_mod_exp():
    assert mod_exp(2, 3, 7) == 1
    assert mod_exp(2, 20, 1373) == 977
    assert mod_exp(3, 20, 1000) == 401
    assert mod_exp(5, 20, 1000) == 625
    with pytest.raises(ValueError):
        mod_exp(2, -1, 1)


# tests for core RSA (textbook) primitives: sign and verify
def test_RSA_textbook():
    key = VRF_keyGen()
    PK = key.public_key()
    m = random.randint(0, 2 ** 256 - 1)
    # alpha=i2bytes(a)
    # alpha = b'hello world'
    # m = bytes2ip(alpha)

    # test textbook signature
    c1 = RSASP1(key, m)
    t1 = RSAVP1(PK, c1)
    assert m == t1
    # test textbook encryption
    c2 = RSAVP1(PK, m)
    t2 = RSASP1(key, c2)
    assert m == t2


# tests for the RSA FDH VRF: keygen, prove and verify
def test_vrf_keygen():
    # does not need testing. straight product of PyOpenSSL
    with pytest.raises(ValueError):
        VRF_keyGen(2047)


def test_vrf_prove_and_ver():
    key = VRF_keyGen()
    a = random.randint(0, 2 ** 256 - 1)
    alpha = i2bytes(a, 2048)
    # alpha = b'hello world'
    pi = VRF_prove(key, alpha)

    pk = key.public_key()
    ver, beta = VRF_verify(pk, alpha, pi)
    assert ver is True
    # print("beta:\n",beta)

    # also test some verifications that are false
    # verification with the wrong payload
    alpha2 = b'hello, world2!'
    ver2, beta2 = VRF_verify(pk, alpha2, pi)
    assert ver2 is False

    # verification with the wrong public key
    key2 = VRF_keyGen()
    pk2 = key2.public_key()
    v3, beta3 = VRF_verify(pk2, alpha, pi)
    assert v3 is False


# serialize
def test_serialize_and_ver():
    key = VRF_keyGen()
    a = random.randint(0, 2 ** 256 - 1)
    alpha = i2bytes(a, 2048)
    # alpha = b'hello world'
    pi = VRF_prove(key, alpha)

    PK = key.public_key()
    s = serialize_proof(PK, alpha, pi)
    dpk, dalpha, dpi = deserialize_proof(s)
    b, _ = VRF_verify(dpk, dalpha, dpi)
    assert b is True

    # Role distribution


def test_roledist():
    roles = {'a': .33, 'c': .43, 'b': .24}
    domain_size = 1000
    rd = VRFDistribution(roles, domain_size)
    assert 'a' == rd.role(0)
    assert 'a' == rd.role(1)
    assert 'a' == rd.role(330)
    assert 'c' == rd.role(331)
    assert 'c' == rd.role(760)
    assert 'c' == rd.role(333)
    assert 'b' == rd.role(956)
    assert 'b' == rd.role(1000)
    with pytest.raises(ValueError):
        rd.role(-1)
    with pytest.raises(ValueError):
        rd.role(domain_size + 1)

    with pytest.raises(TypeError):
        VRFDistribution({"abc": .33, "def": .33, 1: .34})

    with pytest.raises(ValueError):
        VRFDistribution({"abc": -1, "def": 1, "g": 1})

    rdsha = VRFDistribution(roles, 2 ** 32)
    assert 'c' == rdsha.role(2 ** 31)


# sortition
def test_sortition():
    key = VRF_keyGen()
    dist = VRFDistribution({'a': .2, 'c': .3, 'b': .5})
    sortition = VRFSortition(dist)
    a = random.randint(0, 2 ** 256 - 1)
    alpha = i2bytes(a, 2048)
    # alpha=b'hello world'

    r, proof = sortition.sort_and_prove(key, alpha)
    assert sortition.verify(proof, r) is True

    if r == 'a':
        r2 = 'b'
    else:
        r2 = 'a'
    assert sortition.verify(proof, r2) is False
