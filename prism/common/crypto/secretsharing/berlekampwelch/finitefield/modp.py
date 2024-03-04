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

from .euclidean import extendedEuclideanAlgorithm
from .numbertype import FieldElement, memoize, typecheck


# so all IntegersModP are instances of the same base class
class _Modular(FieldElement):
    pass


@memoize
def IntegersModP(p):
    # assume p is prime

    class IntegerModP(_Modular):
        def __init__(self, n):
            try:
                self.n = int(n) % IntegerModP.p
            except:
                raise TypeError("Can't cast type %s to %s in __init__" % (type(n).__name__, type(self).__name__))

            self.field = IntegerModP

        @typecheck
        def __add__(self, other):
            return IntegerModP(self.n + other.n)

        @typecheck
        def __sub__(self, other):
            return IntegerModP(self.n - other.n)

        @typecheck
        def __mul__(self, other):
            return IntegerModP(self.n * other.n)

        def __neg__(self):
            return IntegerModP(-self.n)

        @typecheck
        def __eq__(self, other):
            return isinstance(other, IntegerModP) and self.n == other.n

        @typecheck
        def __ne__(self, other):
            return isinstance(other, IntegerModP) is False or self.n != other.n

        @typecheck
        def __divmod__(self, divisor):
            q, r = divmod(self.n, divisor.n)
            return (IntegerModP(q), IntegerModP(r))

        def inverse(self):
            # need to use the division algorithm *as integers* because we're
            # doing it on the modulus itself (which would otherwise be zero)
            x, y, d = extendedEuclideanAlgorithm(self.n, self.p)

            if d != 1:
                raise Exception("Error: p is not prime in %s!" % (self.__name__))

            return IntegerModP(x)

        def __abs__(self):
            return abs(self.n)

        def __str__(self):
            return str(self.n)

        def __repr__(self):
            return '%d (mod %d)' % (self.n, self.p)

        def __int__(self):
            return self.n

    IntegerModP.p = p
    IntegerModP.__name__ = 'Z/%d' % (p)
    IntegerModP.englishName = 'IntegersMod%d' % (p)
    return IntegerModP


if __name__ == "__main__":
    mod7 = IntegersModP(7)
