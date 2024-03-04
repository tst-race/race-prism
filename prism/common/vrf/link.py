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
import hashlib
import os


def is_link_compatible(a_pseudonym: bytes, b_pseudonym: bytes, probability=0.3) -> bool:
    if a_pseudonym == b_pseudonym:
        return False
    pseudonyms = sorted([a_pseudonym.hex(), b_pseudonym.hex()])
    joined = "".join(pseudonyms).encode("utf-8")
    sha = hashlib.sha256(joined).digest()
    value = int.from_bytes(sha, byteorder="big", signed=False)
    threshold = (2**256 - 1) * probability
    return value < threshold


def test_link_compatibility():
    num_tests = 1000000
    probability = 0.95
    hits = 0

    for _ in range(num_tests):
        a = os.urandom(32)
        b = os.urandom(32)
        if is_link_compatible(a, b, probability):
            hits += 1

    min_hits = (probability * 0.9) * num_tests
    max_hits = (probability * 1.1) * num_tests
    print(f"Total hits: {hits}/{num_tests}")
    assert min_hits < hits < max_hits


if __name__ == "__main__":
    test_link_compatibility()
