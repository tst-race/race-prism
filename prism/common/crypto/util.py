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
import os
from Crypto.Random import get_random_bytes

NONCE_BYTES = 12
AES_KEY_BYTES = 32


def make_nonce():
    return os.urandom(NONCE_BYTES)


def make_aes_key():
    return get_random_bytes(AES_KEY_BYTES)
