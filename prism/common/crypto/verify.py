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
try:
    import cryptography
    CRYPTOGRAPHY_AVAILABLE = True
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    import cryptography.x509 as x509
    from prism.common.crypto.server_rsa import ServerRSAPrivateKey
except:
    CRYPTOGRAPHY_AVAILABLE = False
import structlog
from typing import Optional

from prism.common.message import PrismMessage, TypeEnum
from prism.common.vrf.sortition import VRFSortition

LOGGER = structlog.get_logger("prism.verify")


def is_valid_server(server_cert_bytes: bytes, root_cert) -> bool:
    if not server_cert_bytes:
        return False
    server_cert = x509.load_pem_x509_certificate(server_cert_bytes)
    try:
        root_cert.public_key().verify(server_cert.signature,
                                      server_cert.tbs_certificate_bytes,
                                      padding.PKCS1v15(),
                                      server_cert.signature_hash_algorithm)
    except InvalidSignature:
        return False
    return True


def verify_signed_ARK(ark: PrismMessage) -> bool:
    if not ark.certificate or not ark.signature:
        return False
    cert = x509.load_pem_x509_certificate(ark.certificate)
    try:
        cert.public_key().verify(ark.signature,
                                 ark.clone(signature=None).digest(),
                                 padding.PKCS1v15(),
                                 cert.signature_hash_algorithm)
    except InvalidSignature:
        return False
    return True


def verify_ARK(ark_msg: PrismMessage, sortition: Optional[VRFSortition], root_cert):
    if not ark_msg.msg_type == TypeEnum.ANNOUNCE_ROLE_KEY:
        LOGGER.warning(f"Message is not an ARK!", ark=str(ark_msg))
        return False
    if ark_msg.certificate:
        if not CRYPTOGRAPHY_AVAILABLE:
            LOGGER.warning("Cannot properly verify ARK without 'cryptography' library")
            return True
        # a. Verify ARK certificate was signed by root key
        if not is_valid_server(ark_msg.certificate, root_cert):
            LOGGER.warning(f"ARK certificate was not signed by Root CA!", ark=str(ark_msg))
            return False
        # b. Verify ARK signature using ARK public key/certificate; must carry signature at this point
        if not verify_signed_ARK(ark_msg):
            LOGGER.warning(f"ARK signature does not match contents!", ark=str(ark_msg))
            return False
    # c. Verify VRF role
    if sortition and ark_msg.proof:
        return sortition.verify(ark_msg.proof, ark_msg.committee)
    return True


def sign_ARK(ark: PrismMessage, private_key) -> PrismMessage:
    assert ark.msg_type == TypeEnum.ANNOUNCE_ROLE_KEY and ark.signature is None
    if not private_key or not ark.certificate:
        return ark  # do nothing
    certificate = x509.load_pem_x509_certificate(ark.certificate)
    signature = load_pem_private_key(private_key.serialize(), password=None).sign(
        ark.digest(),
        padding.PKCS1v15(),
        certificate.signature_hash_algorithm)
    return ark.clone(signature=signature)
