#  Copyright (c) 2023 SRI International.
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
from cryptography.hazmat.primitives import serialization
import cryptography.x509 as x509
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import *

from prism.common.crypto.halfkey.keyexchange import PrivateKey
from prism.common.crypto.server_rsa import ServerRSAPrivateKey
from prism.common.crypto.x509 import KeyCertificatePair, load_pair
from prism.common.crypto.pki import CommonPKI


class ServerPKI(CommonPKI):
    def __init__(self, config):
        super().__init__(config)
        self.root_key: Optional[ServerRSAPrivateKey] = None
        self.keys_dir = None

        if config.get("pki_root_cert", ""):
            self.keys_dir = Path("/config/keys/")  # TODO: unify between Testbed and Rib deployments!

        # load PRISM Root CA private key (if present)
        root_key_decoded = config.get("pki_root_key", "")
        if root_key_decoded:
            self.root_key = ServerRSAPrivateKey.load_private(root_key_decoded.encode())
            self.logger.debug(f"Created PRISM Root key from config")
            self.keys_dir = None  # reset to None now that we have a master root key!

        # root_key_file = config.get("pki_root_private_key_file", "")
        # if root_key_file:
        #     with open(root_key_file, "rb") as fp:
        #         self.root_key = RSAPrivateKey(private_key=load_pem_private_key(fp.read(), password=None))
        #         self.logger.debug(f"Read PRISM Root Key from {root_key_file}")
        #     self.epoch_prefix = None  # reset to None now that we have a master root key!

        # check that we have everything in place if needed:
        if self.root_cert:
            if not self.root_key and not self.keys_dir:  # TODO: unify between Testbed and Rib deployments!
                raise RuntimeError(f"Cannot use PKI it we have a Root CA but no way of issuing server certificates!")
            self.logger.debug(f"Loaded PRISM Root CA and using " +
                              f"{'Root Key' if self.root_key else list(self.keys_dir.glob('epoch-*'))}")

    def fetch_key_cert_pseudonym(self, epoch_serial_num: int = 0, server_name: str = None) \
            -> Tuple[ServerRSAPrivateKey, Optional[x509.Certificate], bytes]:
        if self.root_cert is None:
            # running without PKI: generate a fresh key and derive pseudonym from it
            cert_key = ServerRSAPrivateKey()
            return cert_key, None, sha256(cert_key.public_key().serialize()).digest()

        if self.root_key:
            # self-issue certificate
            server_pair = KeyCertificatePair(self.root_key, private_key=ServerRSAPrivateKey(), issuer=self.root_cert.issuer)
        else:
            # TODO: unpickle from file or fetch from memory channel/queue!
            self.logger.debug(f"load server key and certificate from {self.keys_dir} " +
                              f"using epoch={epoch_serial_num} and name={server_name}")
            if not self.keys_dir.exists():
                raise RuntimeError(f"No keys dir {self.keys_dir} to load certificate/key for server {server_name}!")
            pair_file = self.keys_dir / f"epoch-{epoch_serial_num:03d}_{server_name}_pair.json"
            if not pair_file.exists():
                raise RuntimeError(f"Cannot find key, certificate pair file {pair_file}")
            server_pair = load_pair(open(pair_file))

        return server_pair.key, server_pair.cert, server_pair.pseudonym


@dataclass
class RoleKeyMaterial:
    private_key: PrivateKey = field(repr=False)
    server_key: ServerRSAPrivateKey = field(repr=False)
    root_cert: x509.Certificate = None
    server_cert: x509.Certificate = None

    def server_cert_as_bytes(self) -> bytes:
        return self.server_cert.public_bytes(serialization.Encoding.PEM) if self.server_cert else b''
