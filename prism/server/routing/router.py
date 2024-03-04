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
from abc import ABCMeta, abstractmethod
from typing import Union, Optional, List

from jaeger_client import SpanContext

from prism.common.constant import TIMEOUT_MS_MAX
from prism.common.message import PrismMessage, LinkAddress


class Router(metaclass=ABCMeta):
    @abstractmethod
    async def send(
            self,
            address: Union[str, LinkAddress],
            message: PrismMessage,
            context: Optional[SpanContext],
            block: bool = False,
            timeout_ms=TIMEOUT_MS_MAX,
            **kwargs
    ) -> bool:
        """
        Send a message to a specific destination address, finding a route there if necessary.
        Returns True if the message was successfully sent (not necessarily received).

        Keyword arguments:
            block -- if true, don't return until the message has been sent (default False)
            timeout_ms -- implies block if nonzero. The number of milliseconds to block before
            returning False (default 0)
        """
        pass

    @abstractmethod
    async def flood(
            self,
            message: PrismMessage,
            context: Optional[SpanContext],
            hops=0,
            **kwargs
    ):
        """
        Flood a message to the entire server network.

        Keyword arguments:
            hops -- the maximum number of hops each copy of the message should take.
        """
        pass

    @abstractmethod
    async def broadcast(
            self,
            message: PrismMessage,
            context: Optional[SpanContext],
            block: bool = False,
            timeout_ms=TIMEOUT_MS_MAX,
            **kwargs
    ):
        pass

    @property
    @abstractmethod
    def broadcast_addresses(self) -> List[LinkAddress]:
        pass

    @abstractmethod
    async def run(self):
        pass
