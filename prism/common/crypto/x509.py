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
from cryptography import x509 as x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, \
    load_pem_private_key, load_pem_public_key
from cryptography.x509.oid import NameOID
from dataclasses import dataclass, InitVar
import datetime
from hashlib import sha256
import json
from typing import *

from prism.common.crypto.server_rsa import ServerRSAPrivateKey


def cert_from_json_str(s: str) -> x509.Certificate:
    return x509.load_pem_x509_certificate(s.encode())


PAIR_KEY = "pair_key"
PAIR_CERT = "pair_cert"


@dataclass(frozen=False)
class KeyCertificatePair:
    key: ServerRSAPrivateKey
    cert: x509.Certificate = None
    private_key: InitVar[ServerRSAPrivateKey] = None
    issuer: InitVar[x509.Name] = None

    def __post_init__(self, private_key, issuer):
        if self.cert:
            return  # no need to generate signed certificate
        if private_key is None:
            # use root key to self-sign root certificate:
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, u"PRISM Root CA"),
            ])
            self.cert = x509.CertificateBuilder() \
                .subject_name(subject) \
                .issuer_name(issuer) \
                .public_key(load_pem_public_key(self.key.public_key().serialize())) \
                .serial_number(x509.random_serial_number()) \
                .not_valid_before(datetime.datetime.utcnow()) \
                .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365)) \
                .add_extension(x509.BasicConstraints(ca=True, path_length=None),
                               critical=True, ) \
                .sign(load_pem_private_key(self.key.serialize(), password=None), hashes.SHA256(), default_backend())
        else:
            # generate a server certificate signed by initial root key, then replace key by given private key
            assert issuer
            self.cert = x509.CertificateBuilder() \
                .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u"PRISM server"), ])) \
                .issuer_name(issuer) \
                .public_key(load_pem_public_key(private_key.public_key().serialize())) \
                .serial_number(x509.random_serial_number()) \
                .not_valid_before(datetime.datetime.utcnow()) \
                .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=60)) \
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(u"localhost")]),
                               critical=False, ) \
                .sign(load_pem_private_key(self.key.serialize(), password=None), hashes.SHA256(), default_backend())
            self.key = private_key

    def __eq__(self, other):
        if not isinstance(other, KeyCertificatePair):
            return False
        return self.key.serialize() == other.key.serialize() and self.cert == other.cert

    @property
    def cert_bytes(self) -> bytes:
        return self.cert.public_bytes(Encoding.PEM)

    @property
    def pseudonym(self) -> bytes:
        return sha256(self.cert.public_key().public_bytes(Encoding.PEM,
                                                          PublicFormat.SubjectPublicKeyInfo)).digest()

    def to_json_dict(self) -> Dict:
        return {PAIR_KEY: self.key.serialize().decode("utf-8"),
                PAIR_CERT: self.cert_bytes.decode("utf-8")}

    def dump(self, fp):
        json.dump(self.to_json_dict(), fp, indent=2)


def load_pair(fp) -> KeyCertificatePair:
    json_dict = json.load(fp)
    return pair_from_json_dict(json_dict)


def pair_from_json_dict(d: Dict) -> KeyCertificatePair:
    if not {PAIR_KEY, PAIR_CERT} == set(d.keys()):
        raise ValueError(f"must have dictionary entries for \"{PAIR_KEY}\" and \"{PAIR_CERT}\" to make pair")
    return KeyCertificatePair(ServerRSAPrivateKey.load_private(d[PAIR_KEY].encode()),
                              cert_from_json_str(d[PAIR_CERT]))
