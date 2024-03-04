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
import base64
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
import hashlib
import json
import math
from typing import Tuple, Optional, Any

from .octets import bytes2ip, i2bytes
from prism.common.crypto.server_rsa import ServerRSAPrivateKey, RSA_KEY_SIZE

# constants section. will be formalized and moved later
# RSA_KEYLEN = 2048  # (bits)
HASH_OUTLEN = 32  # (bytes)


# this file implements VRFs via RSA Full Domain Hash
# From page 3 of this RFC: https://tools.ietf.org/html/draft-irtf-cfrg-vrf-03

# VRF Algorithms
#
#   A VRF comes with a key generation algorithm that generates a public
#   VRF key PK and private VRF key SK.
#
#   The prover hashes an input alpha using the private VRF key SK to
#   obtain a VRF hash output beta
#
#      beta = VRF_hash(SK, alpha)
#
#   The VRF_hash algorithm is deterministic, in the sense that it always
#   produces the same output beta given a pair of inputs (SK, alpha).
#   The prover also uses the private key SK to construct a proof pi that
#   beta is the correct hash output
#
#      pi = VRF_prove(SK, alpha)
#
#   The VRFs defined in this document allow anyone to deterministically
#   obtain the VRF hash output beta directly from the proof value pi as
#
#      beta = VRF_proof_to_hash(pi)
#
#
#   Notice that this means that
#
#      VRF_hash(SK, alpha) = VRF_proof_to_hash(VRF_prove(SK, alpha))
#
#   and thus this document will specify VRF_prove and VRF_proof_to_hash
#   rather than VRF_hash.
#
#   The proof pi allows a Verifier holding the public key PK to verify
#   that beta is the correct VRF hash of input alpha under key PK.  Thus,
#   the VRF also comes with an algorithm
#
#      VRF_verify(PK, alpha, pi)
#
#   that outputs (VALID, beta = VRF_proof_to_hash(pi)) if pi is valid,
#   and INVALID otherwise.


def sha_hash(inp) -> bytes:
    m = hashlib.sha256()
    m.update(inp)
    return m.digest()


# produces an octet string of masklen length based on seed and a hash function (we use sha256)
# the seed is an octet string
# as described in https://tools.ietf.org/html/rfc8017
# def MGF1_ints(seed, masklen):
#    return bytes_to_octet(MGF1(octet_to_bytes(seed),masklen))


# same function as above, but seed is in type bytes
def MGF1(seed: bytes, masklen: int) -> bytes:
    if masklen > (2 ** 32) * HASH_OUTLEN:
        raise ValueError("mask too long")
    T = bytearray()
    for i in range(math.ceil(masklen / HASH_OUTLEN)):
        C = i.to_bytes(4, byteorder='big')
        T += bytearray(sha_hash(seed + C))
    return bytes(T[:masklen])


def mod_mult(a: int, b: int, mod: int) -> int:
    return a * b % mod


def mod_exp(b: int, power: int, mod: int) -> int:
    # the recursive way blows out Python's stack with numbers so large
    # need to do this iteratively
    if power < 0:
        raise ValueError("invalid power")
    assert (power >= 0)
    if power == 0:
        return 1
    if power == 1:
        return b
    accum = 1
    while power > 1:
        if power % 2 == 1:
            accum = mod_mult(b, accum, mod)
            power = (power - 1) // 2
        else:
            power = power // 2
        b = mod_mult(b, b, mod)
    return mod_mult(b, accum, mod)


def RSASP1(K, m: int) -> int:
    # K is type cryptography key
    # m is type integer (the message representative)
    # return s = m^d mod n
    # NOTES: the spec provides a faster way to perform this computation
    # see it for performance improvements
    sk = K.private_numbers()
    pk = K.public_key()
    public = pk.public_numbers()
    n = public.n
    d = sk.d
    return mod_exp(m, d, n)


def RSAVP1(PK, s: int) -> int:
    # PK is type cryptography rsa public key
    # s is type integer (signature representative)
    # return m = s^e mod n
    pk = PK.public_numbers()
    n = pk.n
    e = pk.e
    return mod_exp(s, e, n)


# serialization functions
# recall that we are using these for cryptographic sortition
def serialize_proof(PK, alpha: bytes, pi: bytes) -> str:
    # PK is type cryptography public key
    pk_serial = PK.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo)
    d = {
        "pk": base64.b64encode(pk_serial).decode('utf8'),
        "alpha": base64.b64encode(alpha).decode('utf8'),
        "proof": base64.b64encode(pi).decode('utf8')
    }
    return json.dumps(d)


def deserialize_proof(serial: str) -> Tuple[Any, bytes, bytes]:
    # get the encoded proof message and break it into
    # our internal format so that we can verify properly
    # return K, alpha, pi
    d = json.loads(serial)
    pkstr = base64.decodebytes(bytes(d['pk'], encoding='utf8'))
    dalpha = base64.decodebytes(bytes(d['alpha'], encoding='utf8'))
    dpi = base64.decodebytes(bytes(d['proof'], encoding='utf8'))
    pk = serialization.load_pem_public_key(
        pkstr,
        backend=default_backend())
    return pk, dalpha, dpi


# class RSA_FDH_VRF:


def VRF_keyGen(length=RSA_KEY_SIZE):
    return ServerRSAPrivateKey(None, key_size=length).private_key


def VRF_hash(SK, alpha: bytes) -> bytes:
    pi = VRF_prove(SK, alpha)
    return VRF_proof_to_hash(pi)


# def __VRF_proof_to_hash(pi):
# pi is type bytes
#   two_str = i2bytes(2,1) # = 0x02
#  beta = sha_hash(two_str + pi) ## Hash here is sha356
# return beta


def VRF_proof_to_hash(pi: bytes) -> bytes:
    # pi is type bytes
    two_str = i2bytes(2, 1)  # = 0x02
    beta = sha_hash(two_str + pi)  # Hash here is sha256
    return beta


def VRF_prove(sk, alpha: bytes) -> bytes:
    # key is type cryptography key
    # alpha is type bytes
    # spec:
    # one_str = 0x01 = i2osp(1,1)
    # EM = MGF1(one_str || i2osp(k,4) || i2osp(n,k) || alpha , k-1)
    ## recall k is the byte length the rsa modulus n
    # m = os2ip(EM) 
    # s = RSASP1(K,m)
    # pi = i2osp(s,k)
    # return pi
    pk = sk.public_key()
    public = pk.public_numbers()
    n = public.n
    ksize = (sk.key_size) // 8
    EM = MGF1(i2bytes(1, 1) + i2bytes(ksize, 4) + i2bytes(n, ksize) + alpha, ksize - 1)
    m = bytes2ip(EM)
    s = RSASP1(sk, m)
    pi = i2bytes(s, ksize)
    return pi


def VRF_verify(PK, alpha: bytes, pi: bytes) -> Tuple[bool, Optional[bytes]]:
    # PK is type cryptography public rsa key
    # pi is type bytes
    # alpha is type bytes
    # spec:
    # s = os2ip(pi)
    # m = RSAVP1(K,s)
    # EM = i2osp(m,k-1) ## k is the length in octets of the rsa modulus n
    # one_str = 0x01 = i2osp(1,1)
    # EM_check = MGF1(one_str || i2osp(k,4) || i2osp(n,k) || alpha, k-1)
    ## recall k is the bytelen of the rsa modulus
    # return EM == EM_check
    public = PK.public_numbers()
    n = public.n
    ksize = (PK.key_size) // 8
    s = bytes2ip(pi)
    m = RSAVP1(PK, s)

    try:
        EM = i2bytes(m, ksize - 1)
    except OverflowError:
        return False, None

    EM_check = MGF1(i2bytes(1, 1) + i2bytes(ksize, 4) + i2bytes(n, ksize) + alpha, ksize - 1)
    if EM == EM_check:
        return True, VRF_proof_to_hash(pi)
    else:
        return False, None
