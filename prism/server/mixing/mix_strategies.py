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
from abc import abstractmethod, ABCMeta
from enum import Enum
from jaeger_client import SpanContext
from random import expovariate
import structlog
import trio
from typing import List

from prism.common.message import PrismMessage
from prism.common.config import configuration
from ..CS2.roles.abstract_role import AbstractRole


class MixStrategies(Enum):
    DEFAULT = "IdempotentMix"
    POISSON = "PoissonMix"
    POOL = "PoolMix"

    def __repr__(self):
        return self.value


class AbstractMix(metaclass=ABCMeta):
    def __init__(self, role: AbstractRole):
        self.role = role
        self._logger = structlog.getLogger(__name__ + ' > ' + self.__class__.__name__)

    @abstractmethod
    async def mix(self, message: PrismMessage, context: SpanContext) -> SpanContext:
        raise NotImplemented

    async def run(self):
        pass


class IdempotentMix(AbstractMix):
    async def mix(self, message: PrismMessage, context: SpanContext) -> SpanContext:
        with self.role.trace("mix-idempotent", context) as scope:
            scope.debug(f'No mixing for {message} message', msg_type=message.msg_type)
            await trio.sleep(0.0)  # Trio checkpoint
            return scope.context


class PoissonMix(AbstractMix):
    def __init__(self, role: AbstractRole):
        super(PoissonMix, self).__init__(role)
        lambda_value = configuration.get('mix_poisson_lambda', default=1.0)
        self._logger.info(f'Poisson mix initialized with lambda = {lambda_value}')

    async def mix(self, message: PrismMessage, context: SpanContext) -> SpanContext:
        lambda_value = configuration.get('mix_poisson_lambda', default=1.0)
        delay = expovariate(lambda_value)
        with self.role.trace("mix-poisson", context, delay=f'{delay:.2f}s', l=lambda_value) as scope:
            scope.debug(f'Mixing with delay = {delay:.2f}s ' +
                        f'(exponentially distributed with scale = {1/lambda_value:.2f})',
                        delay=delay, l=lambda_value)
            await trio.sleep(delay)
            return scope.context


class PoolMix(AbstractMix):
    async def mix(self, message: PrismMessage, context: SpanContext) -> SpanContext:
        # TODO: implement pool mixing
        # Add message to pool
        return context

    async def run(self):
        while True:
            # Emit messages from pool when necessary
            await trio.sleep(1)


def get_mix(mix_name: str, role: AbstractRole) -> AbstractMix:
    """
    Get mix specified by name.  If none given or name not found, will return the default mix strategy (idempotent).

    :param mix_name: string of the known MixStrategies (e.g., "POISSON" or "POOL")
    :param role: the role to send messages as/through
    :return: mix strategy object inferred from name
    """
    logger = structlog.getLogger(__name__)
    if mix_name is None or mix_name.upper() not in MixStrategies.__members__:
        logger.info(f'Specified mix name {mix_name} not found - selecting DEFAULT mix')
        return get_mix(MixStrategies.DEFAULT.name, role)
    mix_class_name = MixStrategies.__members__[mix_name.upper()].value
    logger.debug(f'Creating mix {mix_name.upper()} as class {mix_class_name}')
    return globals().get(mix_class_name)(role)
