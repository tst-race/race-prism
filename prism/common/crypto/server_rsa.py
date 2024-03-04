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
import cryptography.hazmat.primitives.asymmetric.rsa as rsa
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, NoEncryption, PrivateFormat, \
    load_pem_private_key

RSA_PUBLIC_EXPONENT = 65537
RSA_KEY_SIZE = 2048


class ServerRSAPublicKey:
    def __init__(self, public_key: rsa.RSAPublicKey):
        self.public_key = public_key

    def serialize(self) -> bytes:
        return self.public_key.public_bytes(Encoding.PEM,
                                            PublicFormat.SubjectPublicKeyInfo)

    def __str__(self):
        return f"RSAPublicKey({self.serialize().hex()})"


class ServerRSAPrivateKey:
    def __init__(self, private_key: rsa.RSAPrivateKey = None, key_size: int = RSA_KEY_SIZE):
        if key_size not in [512, 1024, 2048, 4096]:
            raise ValueError("RSA key size must be in [512, 1024, 2048, 4096]")
        if private_key:
            self.private_key: rsa.RSAPrivateKey = private_key
        else:
            self.private_key: rsa.RSAPrivateKey = rsa.generate_private_key(
                public_exponent=RSA_PUBLIC_EXPONENT,
                key_size=key_size,
                backend=default_backend())

    @staticmethod
    def load_private(data: bytes):
        key = load_pem_private_key(data, password=None, backend=default_backend())
        return ServerRSAPrivateKey(key)

    def public_key(self) -> ServerRSAPublicKey:
        return ServerRSAPublicKey(self.private_key.public_key())

    def serialize(self) -> bytes:
        return self.private_key.private_bytes(Encoding.PEM,
                                              PrivateFormat.TraditionalOpenSSL,
                                              NoEncryption())

    def __str__(self):
        return f"RSAPrivateKey({self.serialize().hex()})"

#
#
# def cert_from_json_str(s: str) -> x509.Certificate:
#     return x509.load_pem_x509_certificate(s.encode())
#
#
# PAIR_KEY = "pair_key"
# PAIR_CERT = "pair_cert"
#
#
# @dataclass(frozen=False)
# class KeyCertificatePair:
#     key: RSAPrivateKey
#     cert: x509.Certificate = None
#     private_key: InitVar[RSAPrivateKey] = None
#     issuer: InitVar[x509.Name] = None
#
#     def __post_init__(self, private_key, issuer):
#         if self.cert:
#             return  # no need to generate signed certificate
#         if private_key is None:
#             # use root key to self-sign root certificate:
#             subject = issuer = x509.Name([
#                 x509.NameAttribute(NameOID.COMMON_NAME, u"PRISM Root CA"),
#             ])
#             self.cert = x509.CertificateBuilder() \
#                 .subject_name(subject) \
#                 .issuer_name(issuer) \
#                 .public_key(self.key.public_key().public_key) \
#                 .serial_number(x509.random_serial_number()) \
#                 .not_valid_before(datetime.datetime.utcnow()) \
#                 .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365)) \
#                 .add_extension(x509.BasicConstraints(ca=True, path_length=None),
#                                critical=True, ) \
#                 .sign(self.key.private_key, hashes.SHA256(), default_backend())
#         else:
#             # generate a server certificate signed by initial root key, then replace key by given private key
#             assert issuer
#             self.cert = x509.CertificateBuilder() \
#                 .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u"PRISM server"), ])) \
#                 .issuer_name(issuer) \
#                 .public_key(private_key.public_key().public_key) \
#                 .serial_number(x509.random_serial_number()) \
#                 .not_valid_before(datetime.datetime.utcnow()) \
#                 .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=60)) \
#                 .add_extension(x509.SubjectAlternativeName([x509.DNSName(u"localhost")]),
#                                critical=False, ) \
#                 .sign(self.key.private_key, hashes.SHA256(), default_backend())
#             self.key = private_key
#
#     def __eq__(self, other):
#         if not isinstance(other, KeyCertificatePair):
#             return False
#         return self.key.serialize() == other.key.serialize() and self.cert == other.cert
#
#     @property
#     def cert_bytes(self) -> bytes:
#         return self.cert.public_bytes(Encoding.PEM)
#
#     @property
#     def pseudonym(self) -> bytes:
#         return sha256(self.cert.public_key().public_bytes(Encoding.PEM,
#                                                           PublicFormat.SubjectPublicKeyInfo)).digest()
#
#     def to_json_dict(self) -> Dict:
#         return {PAIR_KEY: self.key.serialize().decode("utf-8"),
#                 PAIR_CERT: self.cert_bytes.decode("utf-8")}
#
#     def dump(self, fp):
#         json.dump(self.to_json_dict(), fp, indent=2)
#
#
# def load_pair(fp) -> KeyCertificatePair:
#     json_dict = json.load(fp)
#     return pair_from_json_dict(json_dict)
#
#
# def pair_from_json_dict(d: Dict) -> KeyCertificatePair:
#     if not {PAIR_KEY, PAIR_CERT} == set(d.keys()):
#         raise ValueError(f"must have dictionary entries for \"{PAIR_KEY}\" and \"{PAIR_CERT}\" to make pair")
#     return KeyCertificatePair(RivestShamirAdleman.load_private(d[PAIR_KEY].encode()),
#                               cert_from_json_str(d[PAIR_CERT]))
