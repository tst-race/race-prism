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
from pathlib import Path
from typing import *

from prism.common.crypto.server_rsa import ServerRSAPrivateKey
from prism.common.crypto.x509 import KeyCertificatePair
from prism.config.config import Configuration


# creating PKI files to simulate PRISM Root CA (Server Registration Committee) at runtime

def create_server_file(root_pair: KeyCertificatePair, keys_dir: Path, prefix: str):
    server_pair = KeyCertificatePair(root_pair.key, private_key=ServerRSAPrivateKey(), issuer=root_pair.cert.issuer)
    server_pair.dump(open(keys_dir / f"{prefix}_pair.json", "w"))


def generate_pki(config: Configuration, keys_dir: Path = None, prefix: str = "") \
        -> Tuple[Optional[KeyCertificatePair], List[str]]:
    """Generate PKI (approximation) and write as files to configuration directory if requested."""
    epoch_prefixes = []
    root_pair = None
    if config.pki:
        # generate root cert and key:
        root_pair = KeyCertificatePair(ServerRSAPrivateKey())
        config.set_path(["prism_common", "pki_root_cert"], root_pair.cert_bytes.decode("utf-8"))
        if config.pki_epochs == 0:
            # also set root key in server common
            config.set_path(["server_common", "pki_root_key"], root_pair.key.serialize().decode("utf-8"))
        else:
            config.set_path(["server_common", "pki_epochs"], config.pki_epochs)

        # return stub paths to be completed differently later by Testbed and RiB deployments:
        for epoch_i in range(config.pki_epochs):
            # for each pre-configured epoch, generate parent dir "epoch_NNN"
            epoch_prefixes.append(f"epoch-{epoch_i:03d}")

    return root_pair, epoch_prefixes
