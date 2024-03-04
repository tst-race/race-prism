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
import hashlib

from networkManagerPluginBindings import EncPkg

# Common functions used in multiple places

CHECKSUM_BYTES = 16


def digest(data: bytes) -> bytes:
    sha = hashlib.sha256()
    sha.update(data)
    return sha.digest()


def hexdigest(data: bytes) -> str:
    sha = hashlib.sha256()
    sha.update(data)
    return sha.hexdigest()


def hash_enc_package(pkg: EncPkg) -> str:
    return hexdigest(bytes(pkg.getCipherText()))
