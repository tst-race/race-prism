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

import json
import threading
from base64 import b64encode
from pathlib import Path
from typing import Optional

import trio
from jaeger_client import SpanContext
from jaeger_client.constants import SAMPLED_FLAG

from prism.client.client import PrismClient, MessageDelegate
from prism.common.cleartext import ClearText
from prism.common.config import configuration
from prism.common.epoch import EpochCommand
from prism.rib.Log import logInfo, logError, logWarning
from prism.rib.plugin import SRINMPlugin
from networkManagerPluginBindings import PLUGIN_OK, PLUGIN_READY, ClrMsg, PLUGIN_TEMP_ERROR, PLUGIN_NOT_READY


class SRINMClient(SRINMPlugin, MessageDelegate):
    def __init__(self, sdk=None):
        super().__init__(sdk)
        self.client: Optional[PrismClient] = None
        self.plugin_type = "client"
        configuration.is_client = True

    def start(self):
        super().start()
        logInfo("start called")

        self.client = PrismClient(
            transport=self.transport,
            state_store=self.state_store,
            delegate=self,
            genesis_info=self.configure_genesis(),
        )

        threading.Thread(target=self._wrap_async_client).start()
        self.raceSdk.onPluginStatusChanged(PLUGIN_READY)
        logInfo("PRISM client started")

        return PLUGIN_OK

    def _wrap_async_client(self):
        async def start():
            async with trio.open_nursery() as nursery:
                nursery.start_soon(self.client.start)
                nursery.start_soon(self.transport.run)
                nursery.start_soon(self.ready_check)
        try:
            trio.run(start)
        except Exception as _e:
            import traceback
            logError(traceback.format_exc())
            self.raceSdk.onPluginStatusChanged(PLUGIN_NOT_READY)
        finally:
            logInfo("PRISM client has finished")

    def notifyEpoch(self, data: str):
        epoch_command = EpochCommand.parse_request(data)
        if epoch_command:
            self.client.epoch_command(epoch_command)
        else:
            logWarning(f"Bad epoch command: {data}")
        return PLUGIN_OK

    async def ready_check(self):
        while True:
            if self.client.ready:
                await trio.sleep(30.0)
                self.raceSdk.onPluginStatusChanged(PLUGIN_READY)
                logInfo("Reported client as ready")
                return

            await trio.sleep(1.0)

    def processClrMsg(self, handle, msg: ClrMsg):
        context = SpanContext(msg.getTraceId(), msg.getSpanId(), None, SAMPLED_FLAG)

        clear = ClearText(
            message=f"{msg.getNonce()};{msg.getMsg()}",
            sender=msg.getFrom(),
            receiver=msg.getTo(),
            timestamp=msg.getTime(),
            context=context,
        )

        self.client.process_clear_text(clear)

        return PLUGIN_OK

    def message_received(self, cleartext: ClearText):
        nonce, plaintext = cleartext.message.split(";", maxsplit=1)
        nonce = int(nonce)
        logInfo(f"Received message from {cleartext.sender}: {plaintext}")

        clr_msg = ClrMsg(
            plaintext,
            cleartext.sender,
            cleartext.receiver,
            cleartext.timestamp,
            nonce,
            0,
            cleartext.context.trace_id,
            cleartext.context.span_id
        )
        self.raceSdk.presentCleartextMessage(clr_msg)

    # Called on Bob as step 1 of bootstrapping, should finish with call to bootstrapDevice()
    # Write config files to config_path
    def prepareToBootstrap(self, handle, link_id, config_path: str, device_info):
        self.raceSdk.makeDir(config_path)
        out_base = Path(config_path)
        logInfo(f"Preparing Bootstrap package for another client, writing to {out_base}")

        for config in ["prism.json", "client.json"]:
            text = self.read_text(config)
            out_path = out_base / config
            self.write_text(out_path, text)

        arks = [b64encode(server.ark.encode()).decode("utf-8")
                for server in self.client.servers.valid_servers]

        if not arks:
            logError("Not enough ARKs available for bootstrapping.")
            self.raceSdk.bootstrapFailed(handle)
            return PLUGIN_TEMP_ERROR

        bootstrap_text = json.dumps({"bootstrap_arks": arks, "bootstrap_epoch": self.client.current_epoch})
        self.write_text(out_base / "bootstrap.json", bootstrap_text)

        comms_channels = [channel for channel in self.transport.channels if channel.connection_type.client_ok]

        if self.configuration.strict_channel_tags:
            available_tags = set.union(*[channel.tags for channel in comms_channels])
            required_tags = {"ark", "uplink", "downlink"}
            missing_tags = required_tags - available_tags
            if missing_tags:
                logError(f"Missing channel tags: No channels cover {missing_tags}")
                self.raceSdk.bootstrapFailed(handle)
                return PLUGIN_TEMP_ERROR

        self.raceSdk.bootstrapDevice(handle, [c.channel_id for c in comms_channels])
        return PLUGIN_OK

    def onBootstrapPkgReceived(self, persona, pkg):
        return PLUGIN_OK
