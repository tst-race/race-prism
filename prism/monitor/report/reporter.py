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
import io
import os
from contextlib import redirect_stdout

import trio

from .deployment import Deployment


class PrintReporter:
    """Prints the latest report to stdout on a specified interval."""

    def __init__(self, deployment: Deployment, interval: float, clear=True, verbose=False):
        self.deployment = deployment
        self.report_interval_s = interval
        self.clear = clear
        self.verbose = verbose

    async def run(self):
        while True:
            report = self.deployment.generate_report(verbose=self.verbose)
            with io.StringIO() as buf, redirect_stdout(buf):
                report.print_report()
                report_str = buf.getvalue()

            if self.clear:
                os.system("clear")

            print(report_str)

            await trio.sleep(self.report_interval_s)
