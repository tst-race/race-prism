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
from __future__ import annotations

from abc import ABCMeta
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from typing import Dict, Callable, Awaitable, Optional, Union, Set

from jaeger_client import SpanContext
import structlog
import trio
from typing import *

from prism.common.config import configuration
from prism.common.crypto.halfkey import PrivateKey
from prism.common.crypto.server_rsa import ServerRSAPrivateKey
from prism.common.crypto.server_message import decrypt
from prism.common.epoch.genesis import GenesisInfo
from prism.common.logging import MONITOR_STATUS
from prism.common.message import PrismMessage
from prism.common.state import StateStore
from prism.common.tracing import trace_context
from prism.common.transport.epoch_transport import EpochTransport
from prism.common.transport.hooks import MessageTypeHook
from prism.common.util import bytes_hex_abbrv, frequency_limit
from prism.server.server_data import ServerData
from ..ark_store import ArkStore
from ...routing.earkstore import EARKStore
from ...pki import RoleKeyMaterial
from ...routing import LinkStateRouter, Neighborhood

# see: https://blog.yuo.be/2018/08/16/__init_subclass__-a-simpler-way-to-implement-class-registries-in-python/
# for role registry implementation; note that registered (= non-abstract) subclasses in other modules need to be
# imported in __init__.py for this to work

_role_registry: Dict[str, type] = {}


class AbstractRole(metaclass=ABCMeta):
    _role: str

    def __init__(
            self,
            transport: EpochTransport,
            state_store: StateStore,
            sd: ServerData,
            role_keys: RoleKeyMaterial,
            previous_role: Optional[AbstractRole] = None,
            broadcast_tags: Optional[Set[str]] = None,
            genesis_info: Optional[GenesisInfo] = None,
            uplink: bool = False,
            **kwargs,
    ):
        self._transport = transport
        self._state_store = state_store
        assert sd
        self._server_data = sd
        self._key_material = role_keys
        self.previous_role = previous_role
        self.genesis_info = genesis_info

        self.ark_store = ArkStore(self._state_store, self.epoch, self.pseudonym)
        self.neighborhood = Neighborhood(self.epoch)
        self.router = LinkStateRouter(
            self.server_data.id,
            self._state_store,
            self.ark_store,
            self.private_key,
            self._transport,
            self.neighborhood,
            broadcast_tags,
            uplink,
        )

        self.flooding = EARKStore(self.pseudonym, transport=self._transport, router=self.router)

        short_pseudonym = bytes_hex_abbrv(sd.pseudonym, 6)
        self._logger = structlog.get_logger(__name__ + ' > ' + self.__class__.__name__)\
            .bind(role=self.role, server_name=sd.id, pseudonym=short_pseudonym, epoch=sd.epoch)
        # init special file logger for any monitor:
        self._monitor_logger = structlog.get_logger(MONITOR_STATUS)\
            .bind(role=self.role, server_id=sd.id, epoch=sd.epoch, pseudonym=short_pseudonym)

    @classmethod
    def __init_subclass__(cls, registry_name: str = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if registry_name is not None:
            _role_registry[registry_name.upper()] = cls
            cls._role = registry_name

    @property
    def role(self):
        return self.__class__._role

    @property
    def pseudonym(self) -> bytes:
        return self.server_data.pseudonym

    @property
    def epoch(self) -> str:
        return self.server_data.epoch

    @staticmethod
    def create(registry_name: str, **kwargs):
        """
        create the appropriate (subclass) role object from given string
        """
        role_class = _role_registry.get(registry_name.upper())
        if role_class:
            structlog.getLogger(__name__).debug(f'Creating role {registry_name.upper()}')
            return role_class(**kwargs)
        raise ValueError(f'Cannot find class for {registry_name.upper()}')

    @property
    def server_data(self) -> ServerData:
        return self._server_data

    @property
    def private_key(self) -> PrivateKey:
        return self._key_material.private_key

    @property
    def root_certificate(self):
        return self._key_material.root_cert

    @property
    def server_key(self) -> Optional[ServerRSAPrivateKey]:
        return self._key_material.server_key

    def __repr__(self):
        return self.role

    @contextmanager
    def trace(
            self,
            operation: str,
            parent: Optional[Union[PrismMessage, SpanContext]] = None,
            *joining: Union[PrismMessage, SpanContext],
            **kwargs
    ):
        tags = {"role": self.role, "epoch": self.epoch, **kwargs}

        with trace_context(self._logger, operation, parent, *joining, **tags) as scope:
            yield scope

    def monitor_data(self) -> dict:
        return {
            "flood_db_size": len(self.flooding),
            "dropbox_index": self.server_data.dropbox_index,
            "lsp_table_size": len(self.router.network),
            "ongoing_floods": self.router.flood_limiter.borrowed_tokens,
            "queued_floods": self.router.flood_limiter.statistics().tasks_waiting,
            "triggered_floods": self.router.floods_triggered,
            "monitor_ts": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
            "monitor_interval": configuration.log_monitor_interval
        }

    async def alive_loop(self):
        if not configuration.get('log_dir'):
            self._logger.debug(f'done with alive-loop as no log directory specified')
            return

        self._monitor_logger.info(f'Initialized monitor logging')
        while True:
            interval_log = timedelta(seconds=configuration.get('log_monitor_interval', 60))
            interval_trace = timedelta(seconds=configuration.get('log_monitor_trace_interval', 60))
            monitor_data = self.monitor_data()

            if frequency_limit(f"log-monitor-{self.epoch}", interval_log):
                self._monitor_logger.info(f'still alive - sleeping for {interval_log.seconds}s', **monitor_data)

            if frequency_limit(f"log-monitor-trace-{self.epoch}", interval_trace):
                monitor_data["monitor_interval"] = interval_trace.seconds
                with self.trace("alive-loop", **monitor_data):
                    pass

            await trio.sleep(1.0)

    async def handler_loop(
            self,
            nursery: trio.Nursery,
            handler: Callable[[trio.Nursery, PrismMessage, SpanContext], Awaitable[None]],
            require_pseudonym: bool,
            *types
    ):
        if require_pseudonym:
            hook = MessageTypeHook(self.pseudonym, *types)
        else:
            hook = MessageTypeHook(None, *types)
        await self._transport.register_hook(hook)

        while True:
            package = await hook.receive_pkg()
            message = package.message
            context = package.context

            if message.ciphertext and message.half_key and message.nonce:
                with self.trace("handling-decrypted", context) as scope:
                    decrypted = decrypt(message, self.private_key)
                    if not isinstance(decrypted, PrismMessage):
                        scope.warning(f"Decrypted message is not a valid Prism Message: {decrypted} as {self}")
                        continue

                    scope.debug(f'{self} handling decrypted {decrypted.msg_type}')
                    context = scope.context
                    message = decrypted

            await handler(nursery, message, context)

    async def main(self):
        """
        Main entry point to run this role.
        """
        with self.trace("role-choice", pseudonym=bytes_hex_abbrv(self.pseudonym), **self.monitor_data()) as role_scope:
            role_scope.info(f'Chosen role: {self.role}' +
                            (f' ({self.server_data.dropbox_index})'
                             if self.server_data.dropbox_index is not None and self.server_data.dropbox_index >= 0
                             else ''),
                            role=self.role, proof=self.server_data.proof, pseudonym=bytes_hex_abbrv(self.pseudonym),
                            key_material=self._key_material)

        async with trio.open_nursery() as nursery:
            nursery.start_soon(self.alive_loop)  # output alive messages to any monitor
            nursery.start_soon(self.router.run)
            nursery.start_soon(self.flooding.flood_listen_loop)

    def cleanup(self) -> None:
        self._logger.info(f'Goodbye from role {self}')
        # subclasses can do clean up here but should call super().cleanup()

    def debug_dump(self, logger):
        self._transport.debug_dump(logger)
        self.ark_store.debug_dump(logger)
        self.flooding.debug_dump(logger)
        self.router.debug_dump(logger)
