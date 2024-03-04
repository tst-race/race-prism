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

# note: the octet string datatype
# we octet strings are specified by the RSA-FDH-VRF spec
# these strings are lists of elements in base 256
# such that the most significant digit is in the first element of the array
# i.e. 2**42 -1 = [0, 0, 3, 255, 255, 255, 255, 255]
# an analogous representation is the bytes datatype (native in Python)
# which represents elements in base 255 raw encoding
# i.e. 2**42-1 = b'\x03\xff\xff\xff\xff\xff'
# WE USE BYTES in our implementation
# the other conversion functions are left commented for posterity


# bytes directly to int:
def bytes2ip(x: bytes) -> int:
    return int.from_bytes(x, byteorder='big')


# int directly to bytes
def i2bytes(x: int, xLen) -> bytes:
    return x.to_bytes(xLen, byteorder='big')


'''
# the following function converts an integer to an octet string
def i2osp(x, xLen):
    if x >= 256 ** xLen:
        raise ValueError("integer too large")
    digits = []

    while x:
        digits.append(int(x % 256))
        x //= 256
    for i in range(xLen - len(digits)):
        digits.append(0)
    return digits[::-1]

# the following converts an octet string to an integer
def os2ip(X):
    xLen = len(X)
    X = X[::-1]
    x = 0
    for i in range(xLen):
        if X[i] > 255:
            raise ValueError("Octet Element Too Large")
        x = x + X[i] * (256 ** i)
    return x


def octet_to_bytes(x):
    for i in range(len(x)):
        if x[i]>255:
            raise ValueError("Octet Element Too Large")
    return bytes(x)

def bytes_to_octet(x):
    return [b for b in x]
'''
