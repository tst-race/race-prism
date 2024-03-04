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
import inspect
import os
import sys
from pathlib import Path
from subprocess import run, CompletedProcess
from argparse import ArgumentParser
from tempfile import TemporaryDirectory
from typing import List, Union, Dict, Any, Optional

from prism.ribtools.aws_environment import AWSEnvironment
from prism.ribtools.bastion_deployment import BastionDeployment
from prism.ribtools.deployment import Deployment
from prism.ribtools.environment import environment, is_rib, is_bastion
from prism.ribtools.error import PRTError


class Command:
    aliases: List[str] = []

    # If true and using an AWS deployment, forward this command to Bastion instead
    # of running it locally.
    aws_forward: bool = False

    verbose: bool = False
    _args: Dict[str, Any]

    def __init__(self, **kwargs):
        print(f'kwargs[ci_run]={kwargs["ci_run"]}')
        if not kwargs['ci_run'] and not is_bastion:
            self.deployment = Deployment.current()
            self.aws_env = AWSEnvironment.current()

        self._args = kwargs
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def pre_run(self):
        pass

    def run(self):
        pass

    def post_run(self):
        pass

    def subprocess(self, cmd, env=None, cwd=None, capture_output=False, shell=False) -> CompletedProcess:
        if env:
            full_env = os.environ.copy()
            full_env.update(env)
            env = full_env

        cmd = [str(component) for component in cmd]
        if self.verbose:
            print(f"Running {' '.join(cmd)}")
        return run(cmd, env=env, cwd=cwd, capture_output=capture_output, shell=shell)

    def rib_process(self, cmd: List, env=None, cwd=None, capture_output=False) -> CompletedProcess:
        self.ensure_rib()

        if env:
            full_env = os.environ.copy()
            full_env.update(env)
            env = full_env

        docker_cmd = ["docker", "exec", "-it"]
        if cwd:
            docker_cmd.extend(["-w", cwd])
        docker_cmd.append("race-in-the-box")
        docker_cmd.extend(cmd)
        docker_cmd = [str(self.resolve_path(component)) for component in docker_cmd]

        if self.verbose:
            print(f"Running {' '.join(docker_cmd)}")

        return run(docker_cmd, env=env, capture_output=capture_output)

    def is_relative_to(self, path1: Path, path2: Path) -> bool:
        try:
            _ = path1.relative_to(path2)
            return True
        except ValueError:
            return False

    def resolve_path(self, component: Union[Path, str]) -> str:
        if isinstance(component, Path):
            if self.is_relative_to(component, environment.rib_dir):
                return str(Path("/root/.race/rib") / component.relative_to(environment.rib_dir))
            if self.is_relative_to(component, environment.prism_rib_home):
                return str(Path("/code") / component.relative_to(environment.prism_rib_home))
            else:
                return str(component)
        else:
            return str(component)

    def ssh(
        self,
        cmd: List[Union[str, Path]],
        user: str = None,
        host: str = None,
        identity_file: Optional[Union[str, Path]] = None,
        capture_output=True,
    ):
        if not user:
            user = "sri-network-manager"
        if not host:
            host = self.ensure_aws().bastion_ip()
            if not host:
                raise PRTError("Couldn't find Bastion IP.")

        ssh_address = f"{user}@{host}"

        if identity_file:
            ssh_identity = ["-i", identity_file]
            ssh_subprocess = self.subprocess
        else:
            ssh_identity = ["-i", "/root/.ssh/rib_private_key", "-o", "StrictHostKeyChecking=no"]
            ssh_subprocess = self.rib_process

        if cmd[0] == "scp":
            ssh_command = ["scp", *ssh_identity, *cmd[1:], f"{ssh_address}:"]
        elif cmd[0] == "ssh":
            ssh_command = ["ssh", *ssh_identity, ssh_address, *cmd[1:]]
        else:
            raise PRTError(f"Unknown SSH command: {cmd[0]}")

        return ssh_subprocess(ssh_command, capture_output=capture_output)

    def ssh_forward(self, prt_command=None):
        if not prt_command:
            prt_command = ["prt"] + sys.argv[1:]
        cmd = ["ssh", "-t", "bash", "-i", "-c", f"\"{' '.join(prt_command)}\""]
        self.ssh(cmd, capture_output=False)

    def upload_archive(
        self,
        source_dir: Path,
        archive_name: str,
        identity_file: Union[str, Path] = None,
        user: str = None,
        host: str = None,
        extras: List[Path] = None,
    ):
        if not extras:
            extras = []

        with TemporaryDirectory(dir=environment.prism_rib_home) as td:
            temp_dir = Path(td)
            archive_path = temp_dir / archive_name

            result = self.subprocess(["tar", "czf", archive_path, source_dir.name], cwd=source_dir.parent)
            if result.returncode:
                raise PRTError(f"Failed to archive {source_dir} to {archive_name}.")

            return self.ssh(["scp", archive_path, *extras], user=user, host=host, identity_file=identity_file)

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        pass

    @classmethod
    def command_name(cls) -> str:
        return cls.__name__.lower()

    @classmethod
    def help(cls) -> str:
        return cls.description().splitlines()[0]

    @classmethod
    def description(cls) -> str:
        return inspect.cleandoc(cls.__doc__)

    def ensure_current(self) -> Deployment:
        if not self.deployment:
            raise PRTError(f"{self.__class__.command_name()} requires active deployment.")

        return self.deployment

    def ensure_aws(self) -> AWSEnvironment:
        if not self.aws_env:
            raise PRTError(f"{self.__class__.command_name()} requires active AWS environment")

        return self.aws_env

    @classmethod
    def ensure_rib(cls):
        if not cls.rib_running():
            raise PRTError(f"prt {cls.command_name()} requires race-in-the-box to be running.")

    @classmethod
    def rib_running(cls):
        if is_rib:
            return True

        cmd = ["docker", "container", "inspect", "-f", "{{.State.Status}}", "race-in-the-box"]
        result = run(cmd, capture_output=True).stdout.decode("utf-8").strip()
        return result == "running"


class ExternalCommand(Command):
    pass


class RIBCommand(Command):
    def fix_permissions(self):
        if not is_bastion and not is_rib and self.rib_running():
            uid = os.getuid()
            gid = os.getgid()
            self.subprocess(["chown", "-R", f"{uid}:{gid}", "/root/.race/rib"])

    def post_run(self):
        super().post_run()

    def subprocess(self, cmd, env=None, cwd=None, capture_output=False, shell=False) -> CompletedProcess:
        # TODO - support shell commands?
        if is_rib or is_bastion:
            return super().subprocess(cmd, env=env, cwd=cwd, capture_output=capture_output)
        else:
            return self.rib_process(cmd, env=env, cwd=cwd, capture_output=capture_output)

    @staticmethod
    def deployment_boilerplate(deployment: Deployment, *commands: str) -> List[str]:
        cmd = ["rib", "deployment", deployment.mode.name]
        cmd.extend(commands)
        cmd.extend(["--name", deployment.name])
        return cmd

    @staticmethod
    def environment_boilerplate(aws_env: AWSEnvironment, *commands: str) -> List[str]:
        cmd = ["rib", "env", "aws"]
        cmd.extend(commands)
        cmd.extend(["--name", aws_env.name])
        return cmd


class BastionCommand(Command):
    def __init__(self, **kwargs):
        self.deployment = BastionDeployment.current()
        super().__init__(**kwargs)

    def ssh_command(self, hostname: str, cmd: List[str]) -> List[str]:
        ssh_cmd = (
            f"ssh -o StrictHostKeyChecking=no "
            f"-o UserKnownHostsFile=/dev/null "
            f"-o LogLevel=ERROR "
            f"{hostname}".split()
        )
        ssh_cmd.extend(cmd)
        return ssh_cmd
