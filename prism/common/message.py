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

# message format (to be serialized by CBOR)
# want class PrismsMessage to be a dict indexed by field numbers, but also immutable after initialization
# see: https://stackoverflow.com/q/3387691/3816489
#      and answer https://stackoverflow.com/a/39375731/3816489 notes in the summary:
#       * subclassing MutableMapping [or Mapping] is simpler with fewer opportunities for bugs,
#         but slower, takes more memory (see redundant dict), and fails isinstance(x, dict)
#       * subclassing dict is faster, uses less memory, and passes isinstance(x, dict),
#         but it has greater complexity to implement.
# Since it is much easier to write and maintain, we started with 1) and add custom
# methods to support CBOR view.  The final solution makes use of the new `@dataclass` decorator (Python 3.7+)
# that gives a much more concise implementation of an immutable data structure.
from base64 import b64encode, b64decode
import cbor2
from dataclasses import dataclass, field, MISSING
from enum import IntEnum, unique
import hashlib
from inspect import isclass
from ipaddress import ip_address
import os
import sys
import time
from typing import *

MSG_MIME_TYPE = 'application/octet-stream'
MEANING = 'meaning'
COMMENT = 'comment'


@unique
class MyIntEnum(IntEnum):
    pass

    def __format__(self, format_spec):
        # override this until we upgraded to Python 3.8, which should have this issue fixed:
        # https://bugs.python.org/issue37479
        return f"{str(self):{format_spec}}"

    @classmethod
    def to_latex(cls, fp=sys.stdout):
        for member in cls:
            print(f'{member.value} & {member} \\tabularnewline', file=fp)


class TypeEnum(MyIntEnum):
    USER_MESSAGE = 0
    ENCRYPT_EMIX_MESSAGE = 1
    SEND_TO_DROPBOX = 2
    READ_DROPBOX = 3
    ANNOUNCE_ROLE_KEY = 4
    ARK_RESPONSE = 5
    ENCRYPT_USER_MESSAGE = 6
    ENCRYPT_DROPBOX_MESSAGE = 7
    WRITE_DROPBOX = 8
    READ_DROPBOX_RECIPIENTS = 9
    READ_SELECTED_DROPBOX_MESSAGES = 10
    DROPBOX_RECIPIENTS = 11
    SEND_TO_EMIX = 12
    ENCRYPT_DROPBOX_RECIPIENTS = 13
    MPC_REQUEST = 14
    MPC_RESPONSE = 15
    WRITE_OBLIVIOUS_DROPBOX = 16
    READ_OBLIVIOUS_DROPBOX = 17
    READ_OBLIVIOUS_DROPBOX_RESPONSE = 18
    ENCRYPTED_READ_OBLIVIOUS_DROPBOX_RESPONSE = 19
    MESSAGE_FRAGMENT = 20
    ENCRYPTED_MESSAGE_FRAGMENT = 21
    ENCRYPT_PEER_MESSAGE = 22
    MPC_HELLO = 23
    LSP = 24
    LSP_ACK = 25
    LSP_DATABASE_REQUEST = 26
    LSP_DATABASE_RESPONSE = 27
    LSP_HELLO = 28
    LSP_HELLO_RESPONSE = 29
    MPC_ACK = 30
    ARKS = 31
    LSP_FWD = 32
    MPC_HELLO_RESPONSE = 33
    NARK = 34
    CLIENT_REGISTRATION_REQUEST = 35
    CLIENT_REGISTRATION_RESPONSE = 36
    ENCRYPT_REGISTRATION_MESSAGE = 37
    LINK_REQUEST = 38
    FLOOD_MSG = 39
    EPOCH_ARK = 40
    ENCRYPT_LINK_REQUEST = 41
    LINK_REQUEST_ACK = 42
    LSP_FLOOD = 43
    EPOCH_ARK_WRAPPER = 44
    LSP_FWD_ADDR = 45
    ENC_LSP_FWD_ADDR = 46
    LSP_FWD_ADDR_ACK = 47

    def __str__(self):
        if self == self.USER_MESSAGE:
            return "User Message"
        if self == self.ENCRYPT_EMIX_MESSAGE:
            return "Encrypted Emix Message"
        if self == self.SEND_TO_DROPBOX:
            return "Send to Dropbox"
        if self == self.READ_DROPBOX:
            return "Read Dropbox"
        if self == self.ANNOUNCE_ROLE_KEY:
            return "Announcement of Role and Keys (ARK)"
        if self == self.ARK_RESPONSE:
            return "ARK Response"
        if self == self.ENCRYPT_USER_MESSAGE:
            return "Encrypted User Message"
        if self == self.ENCRYPT_DROPBOX_MESSAGE:
            return "Encrypted Dropbox Message"
        if self == self.WRITE_DROPBOX:
            return "Write Dropbox"
        if self == self.READ_DROPBOX_RECIPIENTS:
            return "Read Dropbox Recipients"
        if self == self.READ_SELECTED_DROPBOX_MESSAGES:
            return "Read Selected Dropbox Messages"
        if self == self.DROPBOX_RECIPIENTS:
            return "Dropbox Recipients"
        if self == self.SEND_TO_EMIX:
            return "Send To Emix"
        if self == self.ENCRYPT_DROPBOX_RECIPIENTS:
            return "Encrypted Dropbox Recipients Message"
        if self == self.MPC_REQUEST:
            return "MPC Request"
        if self == self.MPC_RESPONSE:
            return "MPC Response"
        if self == self.WRITE_OBLIVIOUS_DROPBOX:
            return "Write Oblivious Dropbox"
        if self == self.READ_OBLIVIOUS_DROPBOX:
            return "Read Oblivious Dropbox"
        if self == self.READ_OBLIVIOUS_DROPBOX_RESPONSE:
            return "Read Oblivious Dropbox Response"
        if self == self.ENCRYPTED_READ_OBLIVIOUS_DROPBOX_RESPONSE:
            return "Encrypted Read Oblivious Dropbox Response"
        if self == self.MESSAGE_FRAGMENT:
            return "Message Fragment"
        if self == self.ENCRYPTED_MESSAGE_FRAGMENT:
            return "Encrypted Message Fragment"
        if self == self.ENCRYPT_PEER_MESSAGE:
            return "Encrypted Peer Message"
        if self == self.MPC_HELLO:
            return "MPC Hello"
        if self == self.LSP:
            return "LSP"
        if self == self.LSP_ACK:
            return "LSP Ack"
        if self == self.LSP_DATABASE_REQUEST:
            return "LSP Database Request"
        if self == self.LSP_DATABASE_RESPONSE:
            return "LSP Database Response"
        if self == self.LSP_HELLO:
            return "LSP Hello"
        if self == self.LSP_HELLO_RESPONSE:
            return "LSP Hello Response"
        if self == self.MPC_ACK:
            return "MPC ACK"
        if self == self.ARKS:
            return "ARKs"
        if self == self.LSP_FWD:
            return "LSP Forwarding"
        if self == self.MPC_HELLO_RESPONSE:
            return "MPC Hello Response"
        if self == self.NARK:
            return "NARK"
        if self == self.CLIENT_REGISTRATION_REQUEST:
            return "Client Registration Request"
        if self == self.CLIENT_REGISTRATION_RESPONSE:
            return "Client Registration Response"
        if self == self.FLOOD_MSG:
            return "Flooding PRISM Message"
        if self == self.EPOCH_ARK:
            return "Epoch ARK"
        if self == self.ENCRYPT_LINK_REQUEST:
            return "Encrypted Link Request"
        if self == self.LINK_REQUEST:
            return "Link Request"
        if self == self.LINK_REQUEST_ACK:
            return "Link Request ACK"
        if self == self.EPOCH_ARK_WRAPPER:
            return "Epoch ARK (wrapped)"
        if self == self.LSP_FLOOD:
            return "Flood"

        return f"UNKNOWN {self.__class__.__name__} ({self.name})"

    def create(self, **kv):
        return PrismMessage(msg_type=self, **kv)


class CipherEnum(MyIntEnum):
    AES_GCM = 0

    def __str__(self):
        if self == self.AES_GCM:
            return "AES-GCM"
        return f"UNKNOWN {self.__class__.__name__}"


class MessageKeyEncryptionTypeEnum(MyIntEnum):
    IBE_SCHEME = 0

    def __str__(self):  # TODO
        if self == self.IBE_SCHEME:
            return "IBE Scheme"
        return f"UNKNOWN {self.__class__.__name__}"


class HalfKeyTypeEnum(MyIntEnum):
    DIFFIE_HELLMAN = 0
    ECDH = 1

    def __str__(self):
        if self == self.DIFFIE_HELLMAN:
            return "Diffie-Hellman"
        elif self == self.ECDH:
            return "Elliptic Curve Diffie-Hellman"
        return f"UNKNOWN {self.__class__.__name__}"


class DropboxModeType(MyIntEnum):
    SINGLE_SERVER = 0
    MPC_COMMITTEE = 1

    def __str__(self):
        if self == self.MPC_COMMITTEE:
            return "MPC"
        if self == self.SINGLE_SERVER:
            return "single server"
        return f"UNKNOWN {self.__class__.__name__}"


class SecretSharingType(MyIntEnum):
    SHAMIR = 0
    FELDMAN = 1
    FULL = 2

    def __str__(self):
        if self == self.SHAMIR:
            return "Shamir"
        if self == self.FELDMAN:
            return "Feldman"
        if self == self.FULL:
            return "Full Threshold"
        return f"UNKNOWN {self.__class__.__name__}"


class ActionEnum(MyIntEnum):
    ACTION_MODULUS = 0
    ACTION_OFFLINE_INIT = 1
    ACTION_OFFLINE_TRIPLE_HANDLER = 2
    ACTION_OFFLINE_RNDBIT_HANDLER = 3
    ACTION_OPEN_HANDLER = 4
    ACTION_SHARE_HANDLER1 = 5
    ACTION_SHARE_HANDLER2 = 6
    ACTION_STORE = 7
    ACTION_UPDATE = 8
    ACTION_DELETE = 9
    ACTION_RETRIEVE = 10
    ACTION_REFRESH = 11
    ACTION_SHUFFLE = 12
    ACTION_CLEAR = 13
    ACTION_RECOVER_INIT = 14
    ACTION_RECOVER = 15
    ACTION_RECOVER_HANDLER = 16
    ACTION_RECOVER_COMPLETE = 17
    ACTION_CHANGE_STRUCTURE_INIT = 18
    ACTION_CHANGE_STRUCTURE = 19
    ACTION_CHANGE_STRUCTURE_HANDLER = 20
    ACTION_CHANGE_STRUCTURE_COMPLETE = 21
    ACTION_SIZE = 22
    ACTION_REFRESH_HANDLER = 24
    ACTION_FIND_HANDLER = 25
    ACTION_MUL_HANDLER = 26
    ACTION_NEXT_BATCH_TRIPLE = 27
    ACTION_NEXT_BATCH_RNDBIT = 28
    ACTION_SHARE_HANDLER3 = 29
    ACTION_NEXT_BATCH_RNDNUM = 30
    ACTION_MUL_OFFLINE_TRIPLE_HANDLER = 31
    ACTION_MUL_OFFLINE_RNDBIT_HANDLER = 32
    ACTION_RETRIEVE_AND_DELETE = 33
    ACTION_RETRIEVE_FRAGMENT_AND_DELETE = 34
    ACTION_STORE_FRAGMENT = 35
    ACTION_READY = 36
    ACTION_GENERATE_SHARES = 37
    ACTION_MULM_BGW_RAND = 38
    ACTION_MULM_BGW_OPEN = 39
    ACTION_HELLO = 40

    def __str__(self):
        return self.name.replace("ACTION_", "").lower()

    def __repr__(self):
        return str(self)


# -- base class for all custom, possibly nested data classes:

@dataclass(frozen=True)
class CBORFactory:
    """structure that contains (key, value) pairs, indexed by integer values, to
       denote a compact representation of a CBOR-formatted message or message part"""

    pass  # sub-classes specify fields here; use init=False for fixed values and default=None if not required

    def __str__(self):
        return f"<{self.__class__.__name__}: {self.repr_fields()}>"

    def repr_fields(self):
        return {fname: self.format_field(fname)
                for fname, fvalue in self.__dataclass_fields__.items()
                if fvalue.repr and fvalue.init and self.__getattribute__(fname) is not None}

    def format_field(self, fname):
        fvalue = self.__dataclass_fields__[fname]
        fmt = fvalue.metadata.get("format", None)

        val = self.__getattribute__(fname)

        if fmt == "hex":
            return val.hex()
        elif isinstance(val, IntEnum):
            return val.name
        elif isinstance(val, CBORFactory):
            return val.repr_fields()
        else:
            return val

    def as_cbor_dict(self) -> Dict:
        """Create a CBOR dictionary from this data structure using the order of the fields as keys/indices"""

        result = {}
        for index, dc_field in enumerate(self.__dataclass_fields__.values()):
            if self.__getattribute__(dc_field.name) is not None:
                # distinguish these cases with actions:
                # 1) CBOR Factory subclasses => recurse into them
                # 2) IntEnum => cast to int
                # 3) List => if element is CBOR Factory subclass then recurse into them, else simply copy
                # 4) all other cases => simply copy value from ordered dict representation
                if issubclass(dc_field.type if isclass(dc_field.type) else dc_field.type.__class__, CBORFactory):
                    result[index] = self.__getattribute__(dc_field.name).as_cbor_dict()
                elif isinstance(self.__getattribute__(dc_field.name), IntEnum):
                    result[index] = int(self.__getattribute__(dc_field.name))
                elif isinstance(self.__getattribute__(dc_field.name), List):
                    result[index] = [x.as_cbor_dict() if isinstance(x, CBORFactory) else x
                                     for x in self.__getattribute__(dc_field.name)]
                # REMINDER: don't attempt to have Dict here!
                else:
                    result[index] = self.__getattribute__(dc_field.name)  # just copy value
        return result

    def clone(self, **kwargs):
        d = self.as_cbor_dict()
        for key, value in kwargs.items():
            index = self.lookup_field_index(key)
            if index is None:
                continue
            d[index] = value.as_cbor_dict() if isinstance(value, CBORFactory) else value
        return self.from_cbor_dict(d)

    @classmethod
    def from_cbor_dict(cls, d: Dict):
        """Create a new instance from given CBOR dictionary that uses field indices as keys"""
        if d is None:
            return None

        arg_dict = {}
        for index, feld in enumerate(cls.__dataclass_fields__.values()):
            if feld.init:  # field is part of __init__() implementation
                if index in d:  # field index is present in CBOR dictionary
                    if d[index] is None:
                        continue  # no need to add this entry to the arg dictionary
                    if issubclass(feld.type if isclass(feld.type) else feld.type.__class__, CBORFactory):
                        # nested CBOR dict or None
                        if not isinstance(d[index], dict):
                            raise ValueError(f"Expected a dictionary at index={index} when creating new class instance")
                        if feld.type == CBORFactory or feld.type.__class__ == CBORFactory:
                            if 'cls' not in feld.metadata:
                                raise TypeError("cannot create generic CBORFactory, need subclass metadata")
                            # use metadata information to generate class object:
                            arg_dict[feld.name] = globals()[feld.metadata['cls']].from_cbor_dict(d[index])
                        else:
                            arg_dict[feld.name] = feld.type.from_cbor_dict(d[index])
                    elif isinstance(d[index], list):
                        # TODO: Python 3.8 has more inspection capabilities here!
                        #  see: https://stackoverflow.com/a/50101934/3816489
                        args = feld.type.__args__
                        if not args:
                            raise TypeError("need generic list argument to proceed")
                        if isclass(args[0]) and issubclass(args[0], CBORFactory):
                            if args[0] == CBORFactory:
                                if 'cls' not in feld.metadata:
                                    raise TypeError("cannot create generic CBORFactory, need subclass metadata")
                                # use metadata information to generate class object:
                                arg_dict[feld.name] = [globals()[feld.metadata['cls']].from_cbor_dict(x) for x in
                                                       d[index]]
                            else:
                                arg_dict[feld.name] = [args[0].from_cbor_dict(x) for x in d[index]]
                        else:
                            # TODO: change to better introspection of inner list typing when Python > 3.7
                            #  see: https://stackoverflow.com/a/50080269/3816489
                            origin = getattr(args[0], "__origin__", None)
                            if origin is tuple:
                                arg_dict[feld.name] = [tuple(datum) for datum in d[index]]
                            else:
                                arg_dict[feld.name] = d[index]
                    # REMINDER: don't attempt to handle Dict here!
                    else:
                        arg_dict[feld.name] = feld.type(d[index])
        try:
            return cls(**arg_dict)
        except TypeError as e:
            raise ValueError(f'Cannot create an instance of {cls} from {arg_dict}: {e}')

    @classmethod
    def lookup_field_index(cls, field_name: str) -> int:
        """Find CBOR field index for given field name or raise ValueError if field not present"""
        field_names = [feld.name for feld in cls.__dataclass_fields__.values()]
        try:
            return field_names.index(field_name)
        except ValueError:
            return -1

    def data_size(self) -> int:
        return len(self.encode())

    def encode(self) -> bytes:
        return cbor2.dumps(self.as_cbor_dict())

    @classmethod
    def decode(cls, data: bytes):
        msg = cls.from_cbor_dict(cbor2.loads(data))
        return msg

    def to_b64(self) -> str:
        return b64encode(self.encode()).decode("utf-8")

    @classmethod
    def from_b64(cls, b64: str):
        return cls.decode(b64decode(b64.encode("utf-8")))

    @classmethod
    def to_latex(cls, fp=sys.stdout, add_footnote: bool = False):
        """
        Create a table body for typesetting in LaTeX specification.

        The three columns are:
        1. Field Number
        2. Meaning (as found in meta data) - bold face if no default value specified
        3. Type & Comment (as found in meta data)

        If `add_footnote` is True then add footnote(s) to the lines that have no default value specified.
        """
        from typing_inspect import get_origin
        for index, field_instance in enumerate(cls.__dataclass_fields__.values()):
            if MEANING in field_instance.metadata:
                if field_instance.default is MISSING and field_instance.default_factory is MISSING:
                    # emphasize required arguments
                    footnote = f'\\footnote{"{"}\\textsuperscript{"{"}**{"}"} Field is always required{"}"}' \
                        if add_footnote else '\\textsuperscript{**}'
                    meaning = f'{field_instance.metadata[MEANING]}{footnote}'
                else:
                    meaning = f'{field_instance.metadata[MEANING]}'
                origin = 'List of' if get_origin(field_instance.type) == list else field_instance.type.__name__
                print(f'{index} & ' +
                      f'{meaning} & ' +
                      f'{field_instance.metadata["cls"] if "cls" in field_instance.metadata else origin} ' +
                      f'{field_instance.metadata[COMMENT] if COMMENT in field_instance.metadata else ""} ' +
                      f'\\tabularnewline', file=fp)


@dataclass(frozen=True)
class HalfKeyMap(CBORFactory):
    key_type: HalfKeyTypeEnum = field(metadata={MEANING: 'Type',
                                                COMMENT: '(unsigned integer)'})  # 0
    DH_p_value: int = field(default=None, repr=False, metadata={MEANING: 'DH p value',
                                                                COMMENT: 'Bignum'})
    DH_g_value: int = field(default=None, repr=False, metadata={MEANING: 'DH g value',
                                                                COMMENT: 'Bignum'})
    DH_q_value: int = field(default=None, repr=False, metadata={MEANING: 'DH q value',
                                                                COMMENT: 'Bignum'})
    DH_y_value: int = field(default=None, repr=False, metadata={MEANING: 'DH y value (g\\textsuperscript{a} mod p)',
                                                                COMMENT: 'Bignum'})
    ECDH_public_bytes: bytes = field(default=None, repr=False, metadata={MEANING: 'ECDH public key',
                                                                         COMMENT: 'Bignum'})

    def __repr__(self):
        return f"HalfKeyMap<{self.key_type.name}, {self.ECDH_public_bytes.hex()[:6]}>"

    def to_key(self):
        from prism.common.crypto.halfkey.keyexchange import KeySystem
        return KeySystem.load_public(self.as_cbor_dict())

    @staticmethod
    def from_key(key):
        return create_HKM(key.cbor())


@dataclass(frozen=True)
class DebugMap(CBORFactory):
    # unfortunately, Jaeger currently does not support Inject() of BINARY format, so switching to text map
    # see: https://github.com/jaegertracing/jaeger-client-python/issues/224
    # also note: CBOR cannot have generic dictionaries easily nested, so map Dict[str, str] to List[str] where number of
    # elements is an even number and gets understood as alternating (key, value) pairs when using the trace info
    trace_info: List[str] = field(default=None, metadata={MEANING: 'Trace Information',
                                                          COMMENT: 'str (see issue \\#224 of jaeger-client-python)'})
    decryption_key: bytes = field(default=None, repr=False, metadata={MEANING: 'Decryption Key',
                                                                      COMMENT: ''})
    next_hop_name: str = field(default=None, repr=False, metadata={MEANING: 'Next Hop Name',
                                                                   COMMENT: ''})
    tag: str = field(default=None, repr=False, metadata={MEANING: 'Tag',
                                                         COMMENT: ''})

    # NOTE: when we switch to BINARY format, uncomment the following:
    # def get_carrier(self) -> Optional[bytearray]:
    #     if self.trace_info:
    #         return bytearray(self.trace_info)
    #     return None

    def get_carrier(self) -> Optional[Dict[str, str]]:
        if self.trace_info and len(self.trace_info) % 2 == 0:  # length is an even number
            return dict(zip(self.trace_info[::2], self.trace_info[1::2]))
        return None

    # NOTE: when we switch to BINARY format, change to `carrier: bytearray`, `-> bytes`, and `return bytes(carrier)`
    @staticmethod
    def create_trace_info(carrier: Dict) -> List[str]:
        return list(sum(carrier.items(), tuple()))


# TODO: MessageMap (format TBD)
# TODO: KeyshareMap (format TBD)


@dataclass(frozen=True)
class ListenerMap(CBORFactory):
    IP_address: bytes = field(metadata={MEANING: 'IP Address',
                                        "format": "hex",
                                        COMMENT: '(v4 or v6 address)'})  # 0
    port: int = field(metadata={MEANING: 'Port',
                                COMMENT: 'unsigned'})  # 1

    def __str__(self):
        return f"{ip_address(self.IP_address)}:{self.port}"


@dataclass(frozen=True)
class ServerMap(CBORFactory):
    listening_on: List[ListenerMap] = field(metadata={MEANING: 'ListeningOn',
                                                      COMMENT: 'ListenerMap (required but could be empty)'})
    # 0 TODO: debug why ListenerMap does not show?

    def __str__(self):
        return "[{}]".format(', '.join(str(x) for x in self.listening_on))


@dataclass(frozen=True)
class RecipientInfoMap(CBORFactory):
    sequence_number: int = field(metadata={MEANING: 'Sequence Number',
                                           COMMENT: 'unsigned'})  # 0
    opaque_recipient: bytes = field(metadata={MEANING: 'Opaque Recipient',
                                              "format": "hex",
                                              COMMENT: ''})  # 1
    nonce: bytes = field(default=None, repr=False,
                         metadata={MEANING: 'Nonce',
                                   COMMENT: '(omitted if not present in Dropbox database)'})  # 2


@dataclass(frozen=True)
class MessageInfoMap(CBORFactory):
    sequence_number: int = field(metadata={MEANING: 'Sequence Number',
                                           COMMENT: 'unsigned'})  # 0
    message: bytes = field(repr=False, metadata={MEANING: 'Message',
                                                 COMMENT: ''})  # 1


@dataclass(frozen=True)
class SecretSharingMap(CBORFactory):
    sharing_type: SecretSharingType = field(metadata={MEANING: 'Secret sharing type',
                                                      COMMENT: ''})  # 0
    parties: int = field(metadata={MEANING: 'Number of MPC peers',
                                   COMMENT: 'unsigned (should be 3 or greater)'})  # 1
    threshold: int = field(metadata={MEANING: 'Threshold of honest peers',
                                     COMMENT: 'unsigned (should be \\# peers for Full Threshold)'})  # 2
    modulus: int = field(metadata={MEANING: 'Modulus for current MPC operations',
                                   COMMENT: 'Bignum'})  # 3
    p: int = field(default=None, metadata={MEANING: 'P', COMMENT: 'Bignum? (needed for Feldman)'})  # 4
    g: int = field(default=None, metadata={MEANING: 'G', COMMENT: 'Bignum? (needed for Feldman)'})  # 5


@dataclass(frozen=True)
class Share(CBORFactory):
    share: int = field(metadata={MEANING: 'Secret share as number',
                                 COMMENT: 'unsigned int'})
    x: int = field(metadata={MEANING: 'Index',
                             COMMENT: 'unsigned int'})
    coeffcommits: List[int] = field(default=None, repr=False)
    originalcommit: int = field(default=None, repr=False)

    def __repr__(self):
        return f'Share({str(self.share)[:4]}..., x={self.x})'

    def json(self) -> dict:
        return {
            "share": self.share,
            "x": self.x,
        }

    @property
    def is_dummy(self) -> bool:
        return self.x == -1


@dataclass(frozen=True)
class PreproductInfo(CBORFactory):
    batches: List[bytes] = field(metadata={MEANING: 'Batch ID', COMMENT: ''})
    starts: List[int] = field(metadata={MEANING: 'Index of the first element', COMMENT: ''})
    sizes: List[int] = field(metadata={MEANING: 'Total number of elements', COMMENT: ''})

    @property
    def size(self) -> int:
        return sum(self.sizes)


@dataclass(frozen=True)
class MPCMap(CBORFactory):
    action: ActionEnum = field(default=None, metadata={MEANING: 'Action',
                                                       COMMENT: 'MPC Request/Response sub type'})
    request_id: bytes = field(default=None, metadata={MEANING: 'MPC request ID',
                                                      "format": "hex",
                                                      COMMENT: 'for matching responses to requests'})
    origin: str = field(default=None,
                        metadata={MEANING: 'Origin',  # TODO: should this become mandatory for communication?
                                  COMMENT: 'MPC origin of message (source address)'})
    offline_params: List[float] = field(default=None, metadata={MEANING: 'Offline phase parameters such as batch sizes',
                                                                COMMENT: ''})
    share_pseudonym: Share = field(default=None, metadata={MEANING: 'Indexed pseudonym share fragment',
                                                           COMMENT: ''})
    enc_fragment: bytes = field(default=None, repr=False, metadata={MEANING: 'Ciphertext of encrypted message fragment',
                                                                    COMMENT: ''})
    size: int = field(default=None, metadata={MEANING: 'Current length of dropbox table',
                                              COMMENT: ''})
    # TODO: to impose reliability and cancellation (order within operation, ack's, retransmission, timeout...)
    operation_id: bytes = field(default=None, metadata={
        MEANING: 'MPC operation ID',
        "format": "hex",
        COMMENT: 'for tracking sequence numbers, acks, and retransmissions'})
    syn: int = field(default=None)
    ack: int = field(default=None)
    op_success: bool = field(default=None)
    # TODO: these fields are still used in pre-processing phase...
    value: bytes = field(default=None, repr=False, metadata={MEANING: 'Value',
                                                             COMMENT: '(MPC)'})
    value_id: bytes = field(default=None, repr=False, metadata={MEANING: 'Value Id',
                                                                COMMENT: '(MPC)'})
    participants: List[int] = field(default=None, metadata={MEANING: 'Participants in the requested operation.',
                                                            COMMENT: ''})
    target_fragments: List[bytes] = field(default=None,
                                          metadata={MEANING: 'Which fragments to look at in a retrieve op.',
                                                    COMMENT: ''})
    shares: List[Share] = field(default=None, metadata={MEANING: 'Secret shares as part of an MPC op',
                                                        COMMENT: ''})
    preproduct_info: PreproductInfo = field(default=None,
                                            metadata={MEANING: 'Info about the preproduct batch to use for an op',
                                                      COMMENT: ''})

    def __repr__(self):
        return f"MPCMap{self.repr_fields()}"


@dataclass(frozen=True)
class NeighborInfoMap(CBORFactory):
    pseudonym: bytes = field(metadata={MEANING: 'pseudonym',
                                       "format": "hex",
                                       COMMENT: ''})  # 0
    cost: int = field(metadata={MEANING: 'cost',
                                COMMENT: 'unsigned'})  # 1

    def __repr__(self):
        return f"<{self.pseudonym.hex()[:6]} at {self.cost}>"


@dataclass(frozen=True)
class LinkAddress(CBORFactory):
    channel_id: str = field(metadata={MEANING: "Channel GID", COMMENT: ''})  # 0
    link_address: str = field(metadata={MEANING: "Link Address", COMMENT: ''})  # 1

    def __repr__(self):
        return f"<{self.channel_id}: {self.link_address}>"


@dataclass(frozen=True)
class PrismMessage(CBORFactory):
    # fixed fields: init=False to prevent overriding
    # required fields: omit default=
    version: int = field(default=0, init=False,
                         metadata={MEANING: 'Version',
                                   COMMENT: 'unsigned (0 for this specification)'})  # 0
    msg_type: TypeEnum = field(repr=False,
                               metadata={MEANING: 'Type',
                                         COMMENT: '(unsigned integer)'})  # 1
    messagetext: str = field(default=None, metadata={MEANING: 'Message Text',
                                                     COMMENT: 'UTF-8'})  # 2
    cipher: CipherEnum = field(default=None, metadata={MEANING: 'Cipher',
                                                       COMMENT: ''})  # 3
    ciphertext: bytes = field(default=None, repr=False, metadata={MEANING: 'Ciphertext',
                                                                  COMMENT: ''})  # 4
    half_key: HalfKeyMap = field(default=None, repr=False, metadata={MEANING: 'Half-Key',
                                                                     COMMENT: ''})  # 5
    sub_msg: CBORFactory = field(default=None,  # 6
                                 metadata={'cls': 'PrismMessage',
                                           MEANING: 'SubMessage',
                                           COMMENT: ''})  # 6
    name: str = field(default=None, metadata={MEANING: 'Name',
                                              COMMENT: ''})  # 7
    pseudonym: bytes = field(default=None, metadata={MEANING: 'Pseudonym',
                                                     "format": "hex",
                                                     COMMENT: ''})  # 8
    whiteboard_ID: str = field(default=None, metadata={MEANING: 'Whiteboard Id',
                                                       COMMENT: ''})  # 9
    opaque_recipient: bytes = field(default=None, repr=False, metadata={MEANING: 'Opaque Recipient',
                                                                        COMMENT: ''})  # 10
    signature: bytes = field(default=None, repr=False, metadata={MEANING: 'Message Signature',
                                                                 "format": "hex",
                                                                 COMMENT: 'signature over digest w/o debug info'})  # 11
    dropbox_index: int = field(default=None, metadata={MEANING: 'Dropbox Index',
                                                       COMMENT: 'unsigned'})  # 12
    msg_key_encryption_type: \
        MessageKeyEncryptionTypeEnum = field(default=None, metadata={MEANING: 'Message Key Encryption Type',
                                                                     COMMENT: ''})  # 13
    encrypted_msg_key: bytes = field(default=None, repr=False, metadata={MEANING: 'Encrypted Message Key',
                                                                         COMMENT: ''})  # 14
    hop_count: int = field(default=None, metadata={MEANING: 'Hop Count',
                                                   COMMENT: 'unsigned'})  # 15
    certificate: bytes = field(default=None, repr=False, metadata={MEANING: 'Certificate',
                                                                   COMMENT: '(PKCS\\#11)'})  # 16
    nonce: bytes = field(default=None, repr=False, metadata={MEANING: 'Nonce',
                                                             COMMENT: ''})  # 17
    CS_output: bytes = field(default=None, repr=False, metadata={MEANING: 'CS Output',
                                                                 COMMENT: ''})  # 18
    role: str = field(default=None, metadata={MEANING: 'Role',
                                              COMMENT: ''})  # 19
    committee: str = field(default=None, metadata={MEANING: 'Committee',
                                                   COMMENT: ''})  # 20
    expiration: int = field(default=None, metadata={MEANING: 'Expiration',
                                                    COMMENT: 'unsigned (seconds since epoch)'})  # 21
    # set automatically at object creation time if not specified:
    origination_timestamp: int = \
        field(default_factory=lambda: int(time.time()), metadata={MEANING: 'Origination Timestamp',
                                                                  COMMENT: 'unsigned (seconds since epoch)'})  # 22
    keyshare: CBORFactory = field(default=None,
                                  metadata={'cls': 'KeyshareMap',
                                            MEANING: 'Keyshare',
                                            COMMENT: '(format TBD)'})  # 23 TODO: KeyshareMap
    debug_info: DebugMap = field(default=None,
                                 metadata={'cls': 'DebugMap',
                                           MEANING: 'Debug Information',
                                           COMMENT: '(such as tracing)'})  # 24
    servers: List[ServerMap] = field(default=None, metadata={MEANING: 'Servers',
                                                             COMMENT: 'ServerMaps'})  # 25
    pad: bytes = field(default=None, repr=False, metadata={MEANING: 'Pad',
                                                           COMMENT: ''})  # 26
    minimum_transit_time: int = field(default=None, metadata={MEANING: 'Minimum Transit Time',
                                                              COMMENT: 'unsigned (seconds)'})  # 27
    maximum_transit_time: int = field(default=None, metadata={MEANING: 'Maximum Transit Time',
                                                              COMMENT: 'unsigned (seconds)'})  # 28
    sequence_number: int = field(default=None, metadata={MEANING: 'Sequence Number',
                                                         COMMENT: 'unsigned'})  # 29
    max_rows: int = field(default=None, metadata={MEANING: 'Max Rows',
                                                  COMMENT: 'unsigned'})  # 30
    recipients: List[RecipientInfoMap] = field(default=None, metadata={MEANING: 'Recipients',
                                                                       COMMENT: 'RecipientInfoMap'})  # 31
    selected_messages: List[int] = field(default=None, metadata={MEANING: 'Selected Messages',
                                                                 COMMENT: 'unsigned integers'})  # 32
    dropbox_mode: DropboxModeType = field(default=None, metadata={MEANING: 'Dropbox Mode',
                                                                  COMMENT: ''})  # 33
    requested_messages: List[MessageInfoMap] = field(default=None, metadata={MEANING: 'Requested Messages',
                                                                             COMMENT: 'MessageInfoMap'})  # 34
    mpc_map: MPCMap = field(default=None,
                            metadata={'cls': 'MPCMap',
                                      MEANING: 'Nested MPC Data Structure',
                                      COMMENT: ''})  # 35
    hello_list: List[Tuple[int, str]] = field(default=None, metadata={MEANING: 'Pairs of peer index and pseudonyms',
                                                                      COMMENT: ''})  # 36
    transport_seq_no: int = field(default=None, metadata={MEANING: 'Transport Sequence Number',
                                                          COMMENT: 'unsigned'})  # 37
    transport_src_addr: str = field(default=None, metadata={MEANING: 'Transport Source Address',
                                                            COMMENT: ''})  # 38
    enc_dropbox_response_id: bytes = field(default=None, repr=False,
                                           metadata={MEANING: 'Response ID from ENC DB Request',
                                                     COMMENT: ''})  # 39
    secret_sharing: SecretSharingMap = field(default=None, metadata={MEANING: 'Secret sharing configuration',
                                                                     COMMENT: ''})  # 40
    worker_keys: List[HalfKeyMap] = field(default=None, repr=False, metadata={MEANING: 'MPC worker keys',
                                                                              COMMENT: 'Half-Key maps'})  # 41
    submessages: List[CBORFactory] = field(default=None, metadata={'cls': 'PrismMessage',
                                                                   MEANING: 'Submessages',
                                                                   COMMENT: 'PrismMessage'})  # 42
    pseudonym_share: int = field(default=None, metadata={MEANING: 'Pseudonym Share',
                                                         COMMENT: 'Secret Share of a Pseudonym'})  # 43
    from_neighbor: bytes = field(default=None, metadata={MEANING: 'From Neighbor Pseudonym',
                                                         "format": "hex",
                                                         COMMENT: ''})  # 44
    to_neighbor: bytes = field(default=None, metadata={MEANING: 'To Neighbor Pseudonym',
                                                       "format": "hex",
                                                       COMMENT: ''})  # 45
    originator: bytes = field(default=None, metadata={MEANING: 'Originator Pseudonym',
                                                      "format": "hex",
                                                      COMMENT: ''})  # 46
    sender: bytes = field(default=None, metadata={MEANING: 'Sender Pseudonym',
                                                  "format": "hex",
                                                  COMMENT: ''})  # 47
    ttl: int = field(default=None, metadata={MEANING: 'Time-To-Live',
                                             COMMENT: 'unsigned'})  # 48
    micro_timestamp: int = field(default=None, metadata={MEANING: 'Timestamp (microseconds since epoch)',
                                                         COMMENT: 'unsigned'})  # 49
    neighbors: List[NeighborInfoMap] = field(default=None, metadata={MEANING: 'Neighbor Information List',
                                                                     COMMENT: 'NeighborInfoMap'})  # 50
    done: int = field(default=None, metadata={MEANING: 'done if non-zero; not-done if 0 or not present',
                                              COMMENT: 'unsigned'})  # 51
    link_addresses: List[LinkAddress] = field(default=None,
                                              metadata={MEANING: "Information about links that can "
                                                                 "be used to reach a node.",
                                                        COMMENT: ''})  # 52
    party_id: int = field(default=None, metadata={MEANING: 'the index of the peer sending this message',
                                                  COMMENT: ''})  # 53
    dest_party_id: int = field(default=None, metadata={MEANING: 'the index of the peer receiving this message',
                                                       COMMENT: ''})  # 54
    dead_servers: List[bytes] = field(default=None, metadata={MEANING: 'dead server pseudonyms',
                                                              COMMENT: ''})  # 55
    epoch: str = field(default=None, metadata={MEANING: 'the name of the epoch this ARK is from',
                                               COMMENT: ''})  # 56
    proof: str = field(default=None, metadata={MEANING: 'sortition proof string',
                                               COMMENT: ''})  # 57
    broadcast_addresses: List[LinkAddress] = field(default=None,
                                                   metadata={MEANING: "Links that can be used to hear from a node",
                                                             COMMENT: ''})  # 58
    ls_db_size: int = field(default=None,
                            metadata={MEANING: "The size of the node's local linkstate db",
                                      COMMENT: ''})  # 59
    ls_acks: List[int] = field(default=None,
                               metadata={MEANING: "Sequence numbers of messages that have been received."})  # 60
    transport_timestamp: int = field(default=None,
                                     metadata={MEANING: "Time since the epoch (in seconds) when this message was"
                                                        "sent by the transport.",
                                               COMMENT: ''})  # 61
    degraded: bool = field(default=None,
                           metadata={MEANING: "If true, this MPC committee is in a degraded state and cannot reliably"
                                              "respond to user requests",
                                     COMMENT: ''})  # 62

    def __str__(self):
        # do not print empty fields or those that have repr=False
        return f"PrismMessage: {self.msg_type} with {self.repr_fields()}"

    def digest(self) -> bytes:
        """
        Create a SHA256 digest byte string for creating message signatures.
        Note: this excludes any debug info in this message.
        :return: SHA256 digest of this message (without any debug info)
        """
        return hashlib.sha256(self.clone(debug_info=None).encode()).digest()

    def hexdigest(self) -> str:
        """
        Create a SHA256 digest string in hex for comparing message contents.
        Note: this excludes any debug info in this message.
        :return: Hex representation of the SHA256 of this message (without any debug info)
        """
        return hashlib.sha256(self.clone(debug_info=None).encode()).hexdigest()


# -- create various data types as convenience methods:


def create_HKM(public_dict: Dict, hkt: HalfKeyTypeEnum = None) -> HalfKeyMap:
    if hkt is None:
        if 0 in public_dict:  # type is declared
            map_dict = {**public_dict}
        else:  # default to Diffie-Hellman
            map_dict = {**{0: HalfKeyTypeEnum.DIFFIE_HELLMAN}, **public_dict}
    else:
        map_dict = {**{0: hkt}, **public_dict}
    return HalfKeyMap.from_cbor_dict(map_dict)


def create_ARK(certificate: bytes, pseudonym: bytes, role: str, **kwargs) -> PrismMessage:
    nonce = os.urandom(12)
    return TypeEnum.ANNOUNCE_ROLE_KEY.create(**{
        **dict(
            certificate=certificate,
            nonce=str(nonce).encode(),  # as bytes
            pseudonym=pseudonym,
            role=role,),
        **kwargs})
