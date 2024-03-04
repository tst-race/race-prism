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
from prism.rib.Log import logDebug
from prism.rib.common import digest, hash_enc_package
from prism.rib.error import CorruptPackageError
from networkManagerPluginBindings import EncPkg


class Checksum:
    def __init__(self, checksum_bytes: int):
        self.checksum_bytes = checksum_bytes

    #####
    # Message Checksums
    #####

    def checksum(self, data: bytes) -> bytes:
        return digest(data)[0 : self.checksum_bytes]

    def package_data(self, pkg: EncPkg) -> bytes:
        cipher_text = bytes(pkg.getCipherText())
        if self.checksum_bytes:
            claimed_checksum = cipher_text[0 : self.checksum_bytes]
            data = cipher_text[self.checksum_bytes :]
            calculated_checksum = self.checksum(data)

            if calculated_checksum != claimed_checksum:
                logDebug(f"Package: {hash_enc_package(pkg)}")
                logDebug(f"Claimed checksum: {claimed_checksum.hex()}")
                logDebug(f"Calculated checksum: {calculated_checksum.hex()}")
                raise CorruptPackageError()

            return data
        else:
            return cipher_text

    def add_checksum(self, pkg: EncPkg) -> EncPkg:
        if not self.checksum_bytes:
            return pkg

        cipher_text = bytes(pkg.getCipherText())
        checksum = self.checksum(cipher_text)

        return EncPkg(pkg.getTraceId(), pkg.getSpanId(), checksum + cipher_text)
