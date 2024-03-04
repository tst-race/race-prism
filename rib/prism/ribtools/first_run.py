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
from prism.ribtools.command import RIBCommand
from prism.ribtools.environment import environment, BastionEnv, is_rib
from prism.ribtools.error import PRTError


def first_run_setup():
    if isinstance(environment, BastionEnv):
        return

    if not environment.rib_dir:
        raise PRTError("Set up RIB first before running PRT.")

    # Check if PRT setup has already been run
    if environment.prt_dir.exists():
        return

    if is_rib:
        raise PRTError("Please run prt outside RIB, but with a RIB container running for initial setup.")

    comm = RIBCommand()
    comm.ensure_rib()

    print("Performing first-time setup for prt.")
    comm.rib_process(["mkdir", "-p", environment.prt_dir, environment.deployments_dir, environment.environments_dir])
    comm.fix_permissions()
