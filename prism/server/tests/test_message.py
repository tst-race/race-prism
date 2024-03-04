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
from enum import IntEnum
from ipaddress import ip_address
from time import sleep

import pytest
from cbor2 import dumps, loads

from prism.common.message import create_ARK, create_HKM, \
    PrismMessage, TypeEnum, HalfKeyMap, HalfKeyTypeEnum, ListenerMap, ServerMap, DebugMap, SecretSharingMap, \
    SecretSharingType, MPCMap, ActionEnum


@pytest.fixture
def pm():
    return PrismMessage(
        msg_type=TypeEnum.READ_DROPBOX,
        messagetext='Hello World!',
        ciphertext=b'ciphertext',
        name='alice@example.com',
        pseudonym=b'Alice',
        whiteboard_ID='wb01',
        encrypted_msg_key=b'789',
        hop_count=10)


def test_type_enum():
    t = TypeEnum(2)
    assert isinstance(t, TypeEnum)
    assert t == 2, "TypeEnum is also int"

    with pytest.raises(ValueError):
        TypeEnum(100)


def test_ARK():
    ark = create_ARK(b'', half_key=create_HKM({}),
                     name='test ARK', pseudonym=b'bla ba',
                     role='UNDEFINED', committee='I wonder', )
    assert isinstance(ark, PrismMessage)
    assert TypeEnum.ANNOUNCE_ROLE_KEY == ark.msg_type, 'message is of type ARK'


def test_type_hints():
    # wrapping and unwrapping List[int] and Dict...
    lm = ListenerMap(IP_address=ip_address('192.168.33.44').packed, port=1234)
    sm = ServerMap(listening_on=[lm, ListenerMap(IP_address=ip_address('127.0.0.1').packed, port=10)])
    pm = PrismMessage(TypeEnum.DROPBOX_RECIPIENTS, servers=[sm], selected_messages=[3, 2, 1])
    data = dumps(pm.as_cbor_dict())
    message = loads(data)
    sleep(2)
    pmNew = PrismMessage.from_cbor_dict(message)
    assert isinstance(pmNew, PrismMessage)
    assert pm.origination_timestamp == pmNew.origination_timestamp, 'origination timestamp preserved'
    # TODO: fix origination timestamp and then compare!


def test_empty_map():
    # empty server map
    sm = ServerMap(listening_on=[])
    data = dumps(sm.as_cbor_dict())
    message = loads(data)
    assert sm.as_cbor_dict() == message, 'CBOR dumping and loading preserves the map'


def test_map_with_two_entries():
    lm = ListenerMap(IP_address=ip_address('192.168.33.44').packed, port=1234)
    sm = ServerMap([lm, ListenerMap(IP_address=ip_address('127.0.0.1').packed, port=10)])
    data = dumps(sm.as_cbor_dict())
    message = loads(data)
    assert sm.as_cbor_dict() == message, 'CBOR dumping and loading preserves the map'
    smNew = ServerMap.from_cbor_dict(message)
    assert isinstance(smNew, ServerMap), 'newly created message is of type ServerMap'


def test_debug_map():
    carrier = {'uber-trace-id': '9a0cfe62a2a14233:7df423b8a2a5f089:233eecbc8f6db6e0:1'}
    # trace_info = pickle.dumps(list(sum(carrier.items(), tuple())))
    trace_info = list(sum(carrier.items(), tuple()))
    debug_map = DebugMap(trace_info=trace_info)
    dm_dict = debug_map.as_cbor_dict()
    data = dumps(dm_dict)
    assert dm_dict == loads(data), 'CBOR dumping and loading preserves the map'
    message = DebugMap.from_cbor_dict(loads(data))
    assert isinstance(message, DebugMap)
    assert message.trace_info == trace_info
    message_carrier = dict(zip(message.trace_info[::2],
                               message.trace_info[1::2]))
    # unpickled_ti = pickle.loads(message.trace_info)
    # message_carrier = dict(zip(unpickled_ti[::2], unpickled_ti[1::2]))
    assert message_carrier == carrier

    pm = PrismMessage(TypeEnum.ARK_RESPONSE, debug_info=debug_map, messagetext='a test')
    data = dumps(pm.as_cbor_dict())
    assert pm.as_cbor_dict() == loads(data), 'CBOR dumping and loading preserves the map'
    message = PrismMessage.from_cbor_dict(loads(data))
    assert isinstance(message, PrismMessage)
    assert message.debug_info.trace_info == trace_info

    # test other parts of DebugMap:
    debug_map = DebugMap(decryption_key=b'decryption_key', next_hop_name='next hop', tag='a tag')
    pm = PrismMessage(TypeEnum.ARK_RESPONSE, debug_info=debug_map, messagetext='a test')
    data = dumps(pm.as_cbor_dict())
    assert pm.as_cbor_dict() == loads(data), 'CBOR dumping and loading preserves the map'
    message = PrismMessage.from_cbor_dict(loads(data))
    assert isinstance(message, PrismMessage)
    assert message.debug_info.decryption_key == b'decryption_key'

    # cloning:
    new_debug_map = pm.debug_info.clone(decryption_key=b'new_key')
    new_pm = pm.clone(debug_info=new_debug_map)
    assert isinstance(new_pm, PrismMessage)
    assert new_pm.debug_info.decryption_key == b'new_key'
    assert new_pm.debug_info.tag == pm.debug_info.tag, 'preserving other entries in nested CBOR'

    # test removing DebugMap:
    pm_no_debug = pm.clone(debug_info=None)
    assert isinstance(pm_no_debug, PrismMessage)
    assert len(pm.as_cbor_dict()) == len(pm_no_debug.as_cbor_dict()) + 1
    assert pm.hexdigest() == pm_no_debug.hexdigest()


def test_expiration(pm):
    assert isinstance(pm, PrismMessage)
    assert pm.expiration is None
    cloned_msg = pm.clone(expiration=pm.expiration + 42 if pm.expiration else None)
    assert isinstance(cloned_msg, PrismMessage)
    assert cloned_msg.expiration == pm.expiration
    msg = PrismMessage(msg_type=TypeEnum.USER_MESSAGE, expiration=12345)
    assert msg.expiration == 12345
    cloned_msg = msg.clone(expiration=msg.expiration + 42)
    assert msg.expiration + 42 == cloned_msg.expiration


# def test_message(pm):
#     assert pm.msg_type == TypeEnum.READ_DROPBOX
#     assert pm.version == 0
#     assert pm.origination_timestamp is not None
#     msg = create_encrypted(TypeEnum.ENCRYPT_DROPBOX_MESSAGE, b'', HalfKeyMap(HalfKeyTypeEnum.ECDH), b'')
#     assert msg.msg_type == TypeEnum.ENCRYPT_DROPBOX_MESSAGE


def test_exceptions(pm):
    with pytest.raises(TypeError):
        PrismMessage()

    with pytest.raises(ValueError):
        msgDict = pm.as_cbor_dict()
        del msgDict[1]  # remove entry for NON-DEFAULT field!
        PrismMessage.from_cbor_dict(msgDict)


def test_nested_half_key():
    dh_map = HalfKeyMap(HalfKeyTypeEnum.ECDH, ECDH_public_bytes=b'bla bla')
    pm = PrismMessage(TypeEnum.SEND_TO_EMIX, half_key=dh_map)
    pm_cbor = pm.as_cbor_dict()
    assert isinstance(pm_cbor[1], int), "msg type in CBOR is plain int "
    assert not isinstance(pm_cbor[1], IntEnum), "msg type in CBOR is no longer IntEnum"
    data = dumps(pm_cbor)
    message = loads(data)
    pmNew = PrismMessage.from_cbor_dict(message)
    assert isinstance(pmNew, PrismMessage)
    assert pmNew.msg_type == TypeEnum.SEND_TO_EMIX
    assert pm.origination_timestamp == pmNew.origination_timestamp, 'origination timestamps were preserved'
    # now check List[HalfKeyMap]:
    pm = PrismMessage(msg_type=TypeEnum.ANNOUNCE_ROLE_KEY,
                      worker_keys=[dh_map, dh_map])
    data = dumps(pm.as_cbor_dict())
    message = PrismMessage.from_cbor_dict(loads(data))
    assert len(message.worker_keys) == 2
    assert message.worker_keys[1] == dh_map


def test_CBOR(pm):
    msgDict = pm.as_cbor_dict()
    assert len(msgDict) == 10, "10 fields in test message"
    assert isinstance(msgDict, dict)
    data = dumps(msgDict)
    message = loads(data)
    assert msgDict == message, 'CBOR dumping and loading preserves the message dictionary'
    newPM = PrismMessage.from_cbor_dict(message)
    assert isinstance(newPM, PrismMessage), 'newly created message is Prism'
    # NOTE: newPM cannot be equal as the time stamp should be different


def test_origination():
    pm1 = PrismMessage(msg_type=TypeEnum.USER_MESSAGE)
    sleep(1.3)
    pm2 = PrismMessage(msg_type=TypeEnum.ARK_RESPONSE)
    assert pm1.origination_timestamp < pm2.origination_timestamp, 'msg1 originated before msg2'


# def test_submessage():
#     m4 = create_encrypted(TypeEnum.ENCRYPT_DROPBOX_MESSAGE, b'very secret',
#                           HalfKeyMap(key_type=HalfKeyTypeEnum.DIFFIE_HELLMAN), b'pseudonym of DB for Bob')
#     m5 = create_send_to_DB(m4, 1)
#     m5_dict = m5.as_cbor_dict()
#     data = dumps(m5_dict)
#     message = loads(data)
#     assert m5_dict == message, 'CBOR dumping and loading preserves the message dictionary'
#     assert "very secret" == message[6][4].decode(), 'we wrapped a very secret message'
#     m2 = create_encrypted_user(b'hello Bob', b'secret key')
#     m5 = create_send_to_DB(m2, 1, b'pseudonym of Bob')
#     m5_dict = m5.as_cbor_dict()
#     data = dumps(m5_dict)
#     message = loads(data)
#     assert m5_dict == message, 'CBOR dumping and loading preserves the message dictionary'
#     assert "hello Bob" == message[6][4].decode(), 'we wrapped another secret message'
#
#
# def test_submessages():
#     # now test new field 'submessages': List[<PrismMessage>]
#     m1 = PrismMessage(msg_type=TypeEnum.USER_MESSAGE)
#     m2 = create_encrypted_user(b'hello Bob', b'secret key')
#     m5 = create_send_to_DB(m2, 1, b'pseudonym of Bob')
#     envelope = PrismMessage(msg_type=TypeEnum.WRITE_OBLIVIOUS_DROPBOX,
#                             submessages=[m1, m2, None, m5])
#     data = dumps(envelope.as_cbor_dict())
#     message = PrismMessage.from_cbor_dict(loads(data))
#     assert isinstance(message, PrismMessage)
#     assert len(message.submessages) == 4
#     last_msg = message.submessages[-1]
#     assert last_msg == m5
#
#
# def test_enc_emix():
#     # whole sequence of messages 1 - 5 in specification document:
#     m1 = PrismMessage(msg_type=TypeEnum.USER_MESSAGE, messagetext='Hello Bob!', name='alice@example.com')
#     m2 = create_encrypted_user(ciphertext=dumps(m1.as_cbor_dict()), encrypted_key=b'encrypted key')
#     m3 = PrismMessage(msg_type=TypeEnum.WRITE_DROPBOX, sub_msg=m2, pseudonym=b'Bob pseudo')
#     m4 = create_encrypted(TypeEnum.ENCRYPT_DROPBOX_MESSAGE,
#                           ciphertext=dumps(m3.as_cbor_dict()),
#                           half_key_map=create_HKM({0: 0, 4: 1234}),
#                           pseudonym=b'Dropbox pseudo')
#     m5 = PrismMessage(msg_type=TypeEnum.SEND_TO_DROPBOX, sub_msg=m4)
#     m6 = create_encrypted(TypeEnum.ENCRYPT_EMIX_MESSAGE,
#                           ciphertext=dumps(m5.as_cbor_dict()),
#                           half_key_map=create_HKM({0: 0, 4: 2345}),
#                           pseudonym=b'Emix pseudo')
#     data = dumps(m6.as_cbor_dict())
#     message = PrismMessage.from_cbor_dict(loads(data))
#     # now Emix handles and unwraps the message:
#     assert isinstance(message, PrismMessage), 'message from CBOR is indeed PRISM'
#     assert message.msg_type == TypeEnum.ENCRYPT_EMIX_MESSAGE
#     decrypted = PrismMessage.from_cbor_dict(loads(message.ciphertext))
#     assert isinstance(decrypted, PrismMessage), 'decrypted ciphertext is indeed PRISM'
#     assert decrypted.msg_type == TypeEnum.SEND_TO_DROPBOX
#     submessage = PrismMessage.from_cbor_dict(decrypted.sub_msg.as_cbor_dict())
#     assert isinstance(submessage, PrismMessage), 'submessage is indeed PRISM'


def test_ss_maps():
    # passing secret-sharing maps through messages:
    ssobj = SecretSharingMap(sharing_type=SecretSharingType.SHAMIR, parties=5, threshold=4, modulus=123)
    msg = PrismMessage(msg_type=TypeEnum.MPC_RESPONSE, secret_sharing=ssobj)
    data = dumps(msg.as_cbor_dict())
    new_msg = PrismMessage.from_cbor_dict(loads(data))
    assert isinstance(new_msg, PrismMessage), 'message from CBOR is indeed PRISM'
    assert msg == new_msg
    new_ssobj = new_msg.secret_sharing
    assert isinstance(new_ssobj, SecretSharingMap)
    assert new_ssobj.modulus == 123


def test_msg_fields():
    assert PrismMessage.lookup_field_index('foo') == -1

    field_number = PrismMessage.lookup_field_index('debug_info')
    assert field_number == 24


def test_mpc_map():
    mmap = MPCMap(action=ActionEnum.ACTION_MODULUS, origin='foo')
    msg = PrismMessage(msg_type=TypeEnum.MPC_REQUEST, mpc_map=mmap)
    req_id = b'12345'
    cloned_msg = msg.clone(mpc_map=mmap.clone(request_id=req_id, origin='bla'))
    print(f'{cloned_msg.mpc_map}')
    assert isinstance(cloned_msg, PrismMessage)
    assert isinstance(cloned_msg.mpc_map, MPCMap)
    assert cloned_msg.mpc_map.request_id == req_id
    assert cloned_msg.mpc_map.origin == 'bla'


def test_mpc_hello():
    hello_data = [(2, 'foo'), (0, 'bla')]
    msg = PrismMessage(msg_type=TypeEnum.MPC_HELLO, hello_list=hello_data)
    data = dumps(msg.as_cbor_dict())
    new_msg = PrismMessage.from_cbor_dict(loads(data))
    assert isinstance(new_msg, PrismMessage), 'message from CBOR is indeed PRISM'
