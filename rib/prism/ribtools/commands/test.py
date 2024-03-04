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
import shutil
from argparse import ArgumentParser

from prism.ribtools.environment import environment
from .remove import Remove

from ..command import RIBCommand
from ..deployment import Deployment


class Test(RIBCommand):
    """Run the RIB test command."""

    bootstrap: bool = False

    def run(self):
        if self.bootstrap:
            self.bootstrap_integration()
            return
        d = self.ensure_current()
        test_plan_path = d.config_path() / "network-manager-test-plan.json"
        temp_path = environment.prism_rib_home / "test_plans" / "prt-plan.json"
        shutil.copy(test_plan_path, temp_path)
        code_path = temp_path.relative_to(environment.prism_rib_home)

        cmd = ["rib", "deployment", "local", "test", "integrated", "--name", d.name, "--test-plan", code_path]
        self.subprocess(cmd)
        temp_path.unlink(missing_ok=True)

    def bootstrap_integration(self):
        bootstrap_deployment = "network-manager-ci-testing-test_bootstrap"

        d = Deployment.load_named(bootstrap_deployment)
        if not d:
            d = Deployment(bootstrap_deployment)
            d.save()

        if d.path().exists():
            rm_cmd = Remove()
            rm_cmd.name = bootstrap_deployment
            rm_cmd.run()

        cmd = [
            "/race_in_the_box/scripts/tests/test_bootstrap.sh",
            "--verbose",
            "--no-fail",
            f"--deployment-name={bootstrap_deployment}",
            f"--race={environment.race_version}",
            "--linux-client-count=3",
            "--linux-client-uninstalled-count=1",
            "--linux-server-count=6",
            "--run-time=150",
            "--delay-execute=150",
            "--delay-start=0",
            "--network-manager-plugin=prism:/code/release",
            "--linux-app=RaceTestApp:latest:prod",
            "--android-app=RaceClient:latest:prod",
            "--node-daemon=RaceNodeDaemon:latest:prod",
            "--artifact-manager-plugin=PluginArtifactManagerTwoSixCpp:latest:prod",
            "--comms-s2s-channel=twoSixDirectCpp:latest:prod",
            "--comms-c2s-channel=twoSixIndirectCpp:latest:prod",
            "--comms-bootstrap-channel=twoSixBootstrapCpp:latest:prod"
        ]

        self.subprocess(cmd)

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        parser.add_argument(
            "--bootstrap",
            action="store_true",
            help="Run the CI Bootstrap test in a separate deployment."
        )
