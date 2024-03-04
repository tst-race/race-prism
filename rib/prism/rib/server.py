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

import threading
from typing import Optional

import trio

from prism.common.epoch.command import EpochCommand
from prism.server.newserver import PrismServer
from networkManagerPluginBindings import PLUGIN_OK, PLUGIN_READY, PLUGIN_NOT_READY

from prism.rib.Log import logInfo, logError, logWarning
from prism.rib.plugin import SRINMPlugin


class SRINMServer(SRINMPlugin):
    def __init__(self, sdk=None):
        super().__init__(sdk)
        self.server: Optional[PrismServer] = None
        self.plugin_type = "server"

    def start(self):
        super().start()
        logInfo("start called")
        self.server = PrismServer(
            transport=self.transport,
            state_store=self.state_store,
            genesis_info=self.configure_genesis(),
        )
        threading.Thread(target=self._wrap_async_server).start()
        self.raceSdk.onPluginStatusChanged(PLUGIN_READY)
        logInfo("PRISM server started")

        return PLUGIN_OK

    def notifyEpoch(self, data: str):
        command = EpochCommand.parse_request(data)
        if command:
            self.server.epoch_command(command)
        else:
            logWarning("Bad epoch command")
        return PLUGIN_OK

    def _wrap_async_server(self):
        try:
            trio.run(self.server.main)
        except:
            import traceback
            logError(traceback.format_exc())
            self.raceSdk.onPluginStatusChanged(PLUGIN_NOT_READY)
        finally:
            logInfo("PRISM server has finished")
