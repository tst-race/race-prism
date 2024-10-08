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

import fractions
from itertools import zip_longest

from .numbertype import memoize, DomainElement, typecheck


# strip all copies of elt from the end of the list
def strip(L, elt):
    if len(L) == 0: return L

    i = len(L) - 1
    while i >= 0 and L[i] == elt:
        i -= 1

    return L[:i + 1]


# create a polynomial with coefficients in a field; coefficients are in
# increasing order of monomial degree so that, for example, [1,2,3]
# corresponds to 1 + 2x + 3x^2
@memoize
def polynomialsOver(field=fractions.Fraction):
    class Polynomial(DomainElement):
        operatorPrecedence = 2

        @classmethod
        def factory(cls, L):
            return Polynomial([cls.field(x) for x in L])

        def __init__(self, c):
            if type(c) is Polynomial:
                self.coefficients = c.coefficients
            elif isinstance(c, field):
                self.coefficients = [c]
            elif not hasattr(c, '__iter__') and not hasattr(c, 'iter'):
                self.coefficients = [field(c)]
            else:
                self.coefficients = c

            self.coefficients = strip(self.coefficients, field(0))
            self.indeterminate = 't'

        def isZero(self):
            return self.coefficients == []

        def __repr__(self):
            if self.isZero():
                return '0'

            return ' + '.join(['%s %s^%d' % (a, self.indeterminate, i) if i > 0 else '%s' % a
                               for i, a in enumerate(self.coefficients)])

        def __abs__(self):
            return len(self.coefficients)  # the valuation only gives 0 to the zero polynomial, i.e. 1+degree

        def __len__(self):
            return len(self.coefficients)

        def __sub__(self, other):
            return self + (-1 * other)

        def __iter__(self):
            return iter(self.coefficients)

        def __neg__(self):
            return Polynomial([(-1 * a) for a in self])

        def iter(self):
            return self.__iter__()

        def leadingCoefficient(self):
            return self.coefficients[-1]

        def degree(self):
            return abs(self) - 1

        def evaluateAt(self, x):
            if not isinstance(x, self.field):
                x = self.field(x)

            result = self.field(0)
            for coefficient in self.coefficients[::-1]:
                result = result * x + coefficient

            return result

        def __call__(self, x):
            return self.evaluateAt(x)

        @typecheck
        def __eq__(self, other):
            return self.degree() == other.degree() and all([x == y for (x, y) in zip(self, other)])

        @typecheck
        def __ne__(self, other):
            return self.degree() != other.degree() or any([x != y for (x, y) in zip(self, other)])

        @typecheck
        def __add__(self, other):
            newCoefficients = [sum(x) for x in zip_longest(self, other, fillvalue=self.field(0))]
            return Polynomial(newCoefficients)

        @typecheck
        def __mul__(self, other):
            if self.isZero() or other.isZero():
                return Zero()

            newCoeffs = [self.field(0) for _ in range(len(self) + len(other) - 1)]

            for i, a in enumerate(self):
                for j, b in enumerate(other):
                    newCoeffs[i + j] += a * b

            return Polynomial(newCoeffs)

        @typecheck
        def __divmod__(self, divisor):
            quotient, remainder = Zero(), self
            divisorDeg = divisor.degree()
            divisorLC = divisor.leadingCoefficient()

            while remainder.degree() >= divisorDeg:
                monomialExponent = remainder.degree() - divisorDeg
                monomialZeros = [self.field(0) for _ in range(monomialExponent)]
                monomialDivisor = Polynomial(monomialZeros + [remainder.leadingCoefficient() / divisorLC])

                quotient += monomialDivisor
                remainder -= monomialDivisor * divisor

            return quotient, remainder

        @typecheck
        def __truediv__(self, divisor):
            if divisor.isZero():
                raise ZeroDivisionError
            return divmod(self, divisor)[0]

        @typecheck
        def __mod__(self, divisor):
            if divisor.isZero():
                raise ZeroDivisionError
            return divmod(self, divisor)[1]

    def Zero():
        return Polynomial([])

    Polynomial.field = field
    Polynomial.__name__ = '(%s)[x]' % field.__name__
    Polynomial.englishName = 'Polynomials in one variable over %s' % field.__name__
    return Polynomial
