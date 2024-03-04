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
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key, load_pem_private_key
from cryptography.x509.oid import NameOID
import datetime
import json
import pytest

from prism.common.crypto.server_rsa import ServerRSAPrivateKey
from prism.common.crypto.verify import verify_signed_ARK, is_valid_server, sign_ARK
from prism.common.crypto.x509 import PAIR_KEY, KeyCertificatePair, load_pair, pair_from_json_dict
from prism.common.message import create_ARK, PrismMessage


# Generate root key once
@pytest.fixture(scope="session")
def root_key(tmp_path_factory):
    temp_root_key = ServerRSAPrivateKey()
    fn = tmp_path_factory.mktemp("keys") / "root_key.pem"
    fn.write_bytes(temp_root_key.serialize())
    print(f"\nWritten Root CA key to file {fn}")
    with open(fn, "rb") as f:
        return ServerRSAPrivateKey.load_private(f.read())


def test_root_key_json(root_key):
    pem = root_key.serialize()
    pem_str = pem.decode('utf-8')
    pem_to_json = json.dumps({PAIR_KEY: pem_str})
    pem_from_json = json.loads(pem_to_json)
    root_key_from_json = ServerRSAPrivateKey.load_private(pem_from_json[PAIR_KEY].encode())
    assert root_key_from_json.serialize() == root_key.serialize()


@pytest.fixture(scope="session")
def root_pair(root_key, tmp_path_factory) -> KeyCertificatePair:
    return KeyCertificatePair(root_key)


def test_root_pair_json(root_pair):
    rp_dict = root_pair.to_json_dict()
    rp_json = json.dumps(rp_dict)
    dict_from_json = json.loads(rp_json)
    rp_from_json = pair_from_json_dict(dict_from_json)
    assert isinstance(rp_from_json, KeyCertificatePair)
    assert rp_from_json == root_pair


def test_root_cert(root_pair, tmp_path_factory):
    fn = tmp_path_factory.mktemp("keys") / "root_cert.pem"
    fn.write_bytes(root_pair.cert_bytes)
    print(f"\nWritten Root CA certificate to file {fn}")
    with open(fn, "rb") as f:
        root_cert = x509.load_pem_x509_certificate(f.read())
    assert root_cert == root_pair.cert


# Generate a new cert for a PRISM server from that root
@pytest.fixture
def server_pair(root_pair) -> KeyCertificatePair:
    return KeyCertificatePair(root_pair.key, private_key=ServerRSAPrivateKey(), issuer=root_pair.cert.issuer)


def test_server_pair_dump_load(server_pair, tmp_path_factory):
    fn = tmp_path_factory.mktemp("keys") / "server_pair.json"
    server_pair.dump(open(fn, "w"))
    print(f"\nWritten server pair to file {fn}")
    loaded_server_pair = load_pair(open(fn))
    assert server_pair == loaded_server_pair


@pytest.fixture
def ark(server_pair):
    return create_ARK(
        certificate=server_pair.cert_bytes,
        pseudonym=server_pair.pseudonym,
        role="EMIX",)


def test_verify_cert_signed_by_root(root_pair, server_pair):
    root_pair.cert.public_key().verify(server_pair.cert.signature,
                                       server_pair.cert.tbs_certificate_bytes,
                                       padding.PKCS1v15(),
                                       server_pair.cert.signature_hash_algorithm)


def test_is_valid_server(ark, root_pair):
    assert is_valid_server(ark.certificate, root_pair.cert)


def test_invalid_server(root_pair):
    wrong_key = ServerRSAPrivateKey()
    invalid_cert = x509.CertificateBuilder() \
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u"INVALID PRISM server"),])) \
        .issuer_name(root_pair.cert.issuer) \
        .public_key(load_pem_public_key(wrong_key.public_key().serialize())) \
        .serial_number(x509.random_serial_number()) \
        .not_valid_before(datetime.datetime.utcnow()) \
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=60)) \
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(u"invalid")]),
                       critical=False,) \
        .sign(load_pem_private_key(wrong_key.serialize(), password=None), hashes.SHA256(), default_backend())  # sign with wrong key
    invalid_bytes = invalid_cert.public_bytes(serialization.Encoding.PEM)
    assert not is_valid_server(invalid_bytes, root_pair.cert)


def test_ark_cert_signed_by_root(ark, root_pair):
    ark_cert = x509.load_pem_x509_certificate(ark.certificate)
    root_pair.cert.public_key().verify(ark_cert.signature,
                                       ark_cert.tbs_certificate_bytes,
                                       padding.PKCS1v15(),
                                       ark_cert.signature_hash_algorithm)


def test_invalid_signature(ark, root_pair):
    ark_cert = x509.load_pem_x509_certificate(ark.certificate)
    wrong_signature = bytearray(ark_cert.signature)
    wrong_signature[255] ^= 0x01  # flip last bit of last byte
    with pytest.raises(InvalidSignature):
        root_pair.cert.public_key().verify(bytes(wrong_signature),
                                           ark_cert.tbs_certificate_bytes,
                                           padding.PKCS1v15(),
                                           ark_cert.signature_hash_algorithm)


def test_signed_ark(ark, server_pair):
    assert ark.certificate
    signed_ark = sign_ARK(ark, server_pair.key)
    assert ark.origination_timestamp == signed_ark.origination_timestamp
    print(f"\nSignature: {signed_ark.signature.hex()}")
    cbor_data = signed_ark.encode()
    # pretend we are transmitting the message in bytes to receiver:
    decoded_msg = PrismMessage.decode(cbor_data)
    assert verify_signed_ARK(decoded_msg)


def test_unsigned_ark(ark, server_pair):
    new_ark = ark.clone(certificate=b'')
    unsigned_ark = sign_ARK(new_ark, server_pair.key)
    assert new_ark == unsigned_ark


def test_no_server_key(ark):
    unsigned_ark = sign_ARK(ark, None)
    assert ark == unsigned_ark
