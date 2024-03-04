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
import ctypes.util
from functools import reduce
from pathlib import Path
from typing import Optional, Any, List

from prism.common.crypto.ibe.ibe import IdentityBasedEncryption
from ._bfibe import ffi


class BonehFranklin(IdentityBasedEncryption):
    _lib: Any = None

    def __init__(self, public_params, identity: str = None, private_key=None, system_secret=None):
        super().__init__(identity)
        self.key = private_key
        self._public_params = public_params
        self._system_secret = system_secret

    @property
    def can_encrypt(self) -> bool:
        return self._public_params is not None

    @property
    def can_decrypt(self) -> bool:
        return self.key is not None and self._public_params is not None

    @property
    def public_params(self) -> str:
        return self._format_public_params(self._public_params)

    @property
    def system_secret(self) -> Optional[str]:
        if self._system_secret is None:
            return None
        return self._format_system_secret(self._system_secret)

    @property
    def security_level(self) -> int:
        return int(self.public_params.splitlines(False)[0].split()[1])

    def encrypt_raw(self, address: str, plaintext: bytes) -> bytes:
        assert self._public_params is not None
        return_byte_count = ffi.new("int *")
        ct_pointer = self.lib().encrypt_ibe(
            self._public_params,
            address.encode("utf-8"),
            plaintext,
            len(plaintext),
            return_byte_count
        )
        ciphertext = ffi.buffer(ct_pointer, return_byte_count[0])
        return bytes(ciphertext)

    def decrypt_raw(self, ciphertext: bytes) -> Optional[bytes]:
        assert self._public_params is not None, self.key is not None
        return_byte_count = ffi.new("int *")
        pt_pointer = self.lib().decrypt_ibe(
            self._public_params,
            self.key,
            ciphertext,
            len(ciphertext),
            return_byte_count
        )
        plaintext = ffi.buffer(pt_pointer, return_byte_count[0])
        return bytes(plaintext)

    def generate_private_key(self, address: str) -> str:
        assert self._public_params is not None, self._system_secret is not None
        result = self.lib().generate_private_key(self._public_params, self._system_secret, address.encode("utf-8"))
        return ffi.string(result).decode("utf-8")

    def load_private_key(self, private_key: str):
        self.key = self._parse_private_key(self._public_params, private_key)

    def load_private_keys(self, *private_keys: List[str]):
        self.key = self._parse_private_key(self._public_params, self.sum_secrets(self.public_params, *private_keys))

    @classmethod
    def add_secrets(cls, public_params: str, secret1: str, secret2: str) -> str:
        """Adds together two secret keys under the current encryption"""
        _params = cls._parse_public_params(public_params)
        result = cls.lib().add_secret(_params,
                                      secret1.encode("utf-8"),
                                      secret2.encode("utf-8"))
        return ffi.string(result).decode("utf-8")

    @classmethod
    def sum_secrets(cls, public_params, secrets: List[str]) -> str:
        return reduce(lambda s1, s2: cls.add_secrets(public_params, s1, s2), secrets)

    @classmethod
    def add_public(cls, system1: str, system2: str) -> Optional[str]:
        p1 = cls._parse_public_params(system1)
        p2 = cls._parse_public_params(system2)
        result = cls.lib().add_public(p1, p2)
        if result == ffi.NULL:
            return None

        return cls._format_public_params(result)

    @classmethod
    def sum_public(cls, systems: List[str]) -> Optional[str]:
        return reduce(cls.add_public, systems)

    @classmethod
    def load(cls, identity: str, private_key: str, public_params: str):
        params = None
        if public_params:
            params = cls._parse_public_params(public_params)
        key = None
        if private_key:
            key = cls._parse_private_key(params, private_key)
        return BonehFranklin(identity=identity, private_key=key, public_params=params)

    @classmethod
    def load_multi(cls, identity: str, private_keys: List[str], public_params: List[str]):
        params = cls.sum_public(*public_params)
        key = cls.sum_secrets(params, private_keys)
        return cls.load(identity, key, params)

    @classmethod
    def generate(cls, security_level: int) -> BonehFranklin:
        if security_level not in range(1, 6):
            raise ValueError(f"Valid security levels are in the range [1,5].")

        lib = cls._find_lib()
        return_params = ffi.new("void **")
        return_secret = ffi.new("void **")
        lib.generate_system(security_level, return_params, return_secret)

        return BonehFranklin(public_params=return_params[0], system_secret=return_secret[0])

    @classmethod
    def generate_shard(cls, base: BonehFranklin) -> BonehFranklin:
        lib = cls._find_lib()
        return_params = ffi.new("void **")
        return_secret = ffi.new("void **")
        lib.generate_shard(base._public_params, return_params, return_secret)

        return BonehFranklin(public_params=return_params[0], system_secret=return_secret[0])

    @classmethod
    def load_generator(cls, params_str: str, secret_str: str) -> BonehFranklin:
        params = cls._parse_public_params(params_str)
        secret = cls.parse_system_secret(secret_str)
        return BonehFranklin(public_params=params, system_secret=secret)

    @classmethod
    def lib(cls):
        if not cls._lib:
            cls._lib = cls._find_lib()
        return cls._lib

    @classmethod
    def _find_lib(cls):
        parent_dir = Path(__file__).parent
        local_bfibe = parent_dir / "libbfibe.so"

        # If libbfibe is packed in with this module, then load it directly rather than using the system search path.
        if local_bfibe.exists():
            return ffi.dlopen(str(local_bfibe.absolute()))
        else:
            return ffi.dlopen(ctypes.util.find_library("bfibe"))

    @classmethod
    def available(cls) -> bool:
        try:
            vars(cls.lib())
            return True
        except:
            return False

    @classmethod
    def _format_public_params(cls, params) -> str:
        return ffi.string(cls.lib().format_system_params(params)).decode("utf-8")

    @classmethod
    def _parse_public_params(cls, param_str: str):
        return cls.lib().parse_system_params(param_str.encode("utf-8"))

    @classmethod
    def _parse_private_key(cls, params, key: str):
        return cls.lib().parse_private_key(params, key.encode("utf-8"))

    @classmethod
    def _format_system_secret(cls, secret) -> str:
        return ffi.string(cls.lib().format_system_secret(secret)).decode("utf-8")

    @classmethod
    def parse_system_secret(cls, secret: str):
        return cls.lib().parse_system_secret(secret.encode("utf-8"))


def build_api():
    """
    Generates the CFFI API stub file _bfibe.py in this directory.
    Run whenever bfibe/include/api.h changes.
    """
    from cffi import FFI
    ffibuilder = FFI()
    ffibuilder.set_source("_bfibe", None)
    from prism.cli.repo import REPO_ROOT
    api_h = REPO_ROOT / "bfibe" / "include" / "api.h"
    ffibuilder.cdef(api_h.read_text())
    ffibuilder.compile(tmpdir=Path(__file__).parent, verbose=True)
    print("Refreshed stubs.")


def test():
    s1 = BonehFranklin.generate(3)
    s2 = BonehFranklin.generate_shard(s1)
    s3 = BonehFranklin.generate(3)

    bob_pk = s1.generate_private_key("bob")
    bob_pk2 = s2.generate_private_key("bob")
    assert(bob_pk != bob_pk2)

    pub = BonehFranklin.add_public(s1.public_params, s2.public_params)
    assert(pub != s1.public_params)
    assert(BonehFranklin.add_public(s1.public_params, s3.public_params) is None)

    bob_1 = BonehFranklin.load("bob", bob_pk, s1.public_params)
    bob_2 = BonehFranklin.load("bob", bob_pk2, s2.public_params)
    bob_fused = BonehFranklin.load_multi("bob", [bob_pk, bob_pk2], [s1.public_params, s2.public_params])

    def test_enc(ibe):
        message = "Hi Bob"
        emsg = message.encode("utf-8")
        e = ibe.encrypt("bob", emsg)
        d = ibe.decrypt(e)
        assert(d == emsg)

    test_enc(bob_1)
    test_enc(bob_2)
    test_enc(bob_fused)


if __name__ == "__main__":
    build_api()
