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
from contextlib import contextmanager
from pathlib import Path

from prism.ribtools.error import PRTError

from ..command import ExternalCommand
from prism.ribtools.environment import environment, is_bastion

if not is_bastion:
    rib_client_path = environment.prism_rib_home / "client"
    release_path = environment.prism_rib_home / "release"
    artifacts_path = release_path / "artifacts"

    prt_dockerfile = environment.prism_rib_home / "docker" / "Dockerfile.prt"
    prt_docker_image = "prism-prt-artifacts"

    prt_android_dockerfile = rib_client_path / "android" / "Dockerfile"
    prt_android_image = "prism-android"

    linux_arm64_v8a_client_path = artifacts_path / "linux-arm64-v8a-client" / "prism"
    linux_arm64_v8a_server_path = artifacts_path / "linux-arm64-v8a-server" / "prism"

    linux_x86_64_client_path = artifacts_path / "linux-x86_64-client" / "prism"
    linux_x86_64_server_path = artifacts_path / "linux-x86_64-server" / "prism"


    prism_python = environment.repo_home / "prism"
    rib_python = environment.prism_rib_home / "prism"

    source_paths = {
        # x86_64 Client
        "x86_64_client": prism_python / "client",
        "x86_64_client_common": prism_python / "common",
        "x86_64_client_plugin": rib_python / "rib",
        "x86_64_client.json": environment.prism_rib_home / "manifests" / "client.json",
        # arm64-v8a Client
        "arm64_v8a_client": prism_python / "client",
        "arm64_v8a_client_common": prism_python / "common",
        "arm64_v8a_client_plugin": rib_python / "rib",
        "arm64_v8a_client.json": environment.prism_rib_home / "manifests" / "client.json",
        # x86_64 Server
        "x86_64_server": prism_python / "server",
        "x86_64_server_common": prism_python / "common",
        "x86_64_server_client": prism_python / "client",
        "x86_64_server_plugin": rib_python / "rib",
        "x86_64_server.json": environment.prism_rib_home / "manifests" / "server.json",
        # arm64-v8a Server
        "arm64_v8a_server": prism_python / "server",
        "arm64_v8a_server_common": prism_python / "common",
        "arm64_v8a_server_client": prism_python / "client",
        "arm64_v8a_server_plugin": rib_python / "rib",
        "arm64_v8a_server.json": environment.prism_rib_home / "manifests" / "server.json",
        # Config
        "config-generator": environment.prism_rib_home / "config-generator",
        "config": prism_python / "config",
        "config-common": prism_python / "common",
        "config-rib": rib_python / "rib_config",
        # Release Notes
        "RELEASES.md": environment.prism_rib_home / "RELEASES.md",
        # Monitor
        "monitor_requirements.txt": rib_python / "ribtools" / "monitor" / "requirements.txt",
        "monitor": prism_python / "monitor",
        "rib_monitor": rib_python / "ribtools" / "monitor",
    }
    docker_source_paths = {
        "x86_64_client_ibe": Path("/code/bfibe/build/libbfibe.so"),
        "x86_64_server_ibe": Path("/code/bfibe/build/libbfibe.so"),
        "networkManagerPluginBindings.pyi": Path("/code/networkManagerPluginBindings.pyi"),
    }
    prebuilt_paths = {
        "x86_64_client_ibe": Path("bfibe/prebuilt/x86_64/libbfibe.so"),
        "arm64_v8a_client_ibe": Path("bfibe/prebuilt/arm64-v8a/libbfibe.so"),
        "x86_64_server_ibe": Path("bfibe/prebuilt/x86_64/libbfibe.so"),
        "arm64_v8a_server_ibe": Path("bfibe/prebuilt/arm64-v8a/libbfibe.so"),
    }
    release_paths = {
        # x86_64 Client
        "x86_64_client": linux_x86_64_client_path / "client",
        "x86_64_client_common": linux_x86_64_client_path / "common",
        "x86_64_client_plugin": linux_x86_64_client_path / "rib",
        "x86_64_client_ibe": linux_x86_64_client_path / "common" / "crypto" / "ibe" / "libbfibe.so",
        "x86_64_client.json": linux_x86_64_client_path / "manifest.json",
        # arm64-v8a Client
        "arm64_v8a_client": linux_arm64_v8a_client_path / "client",
        "arm64_v8a_client_common": linux_arm64_v8a_client_path / "common",
        "arm64_v8a_client_plugin": linux_arm64_v8a_client_path / "rib",
        "arm64_v8a_client_ibe": linux_arm64_v8a_client_path / "common" / "crypto" / "ibe" / "libbfibe.so",
        "arm64_v8a_client.json": linux_arm64_v8a_client_path / "manifest.json",
        # x86_64 Server
        "x86_64_server": linux_x86_64_server_path / "server",
        "x86_64_server_common": linux_x86_64_server_path / "common",
        "x86_64_server_ibe": linux_x86_64_server_path / "common" / "crypto" / "ibe" / "libbfibe.so",
        "x86_64_server_client": linux_x86_64_server_path / "client",
        "x86_64_server_plugin": linux_x86_64_server_path / "rib",
        "x86_64_server.json": linux_x86_64_server_path / "manifest.json",
        # arm64-v8a Server
        "arm64_v8a_server": linux_arm64_v8a_server_path / "server",
        "arm64_v8a_server_common": linux_arm64_v8a_server_path / "common",
        "arm64_v8a_server_ibe": linux_arm64_v8a_server_path / "common" / "crypto" / "ibe" / "libbfibe.so",
        "arm64_v8a_server_client": linux_arm64_v8a_server_path / "client",
        "arm64_v8a_server_plugin": linux_arm64_v8a_server_path / "rib",
        "arm64_v8a_server.json": linux_arm64_v8a_server_path / "manifest.json",
        # Config
        "config-generator": release_path / "config-generator",
        "config": release_path / "config-generator" / "prism" / "config",
        "config-common": release_path / "config-generator" / "prism" / "common",
        "config-rib": release_path / "config-generator" / "prism" / "rib_config",
        # Release Notes
        "RELEASES.md": release_path / "RELEASES.md",
        "TESTING.md": release_path / "testing" / "README.md",
        # Monitor
        "monitor_requirements.txt": release_path / "testing" / "requirements.txt",
        "monitor": release_path / "testing" / "prism" / "monitor",
        "rib_monitor": release_path / "testing" / "prism" / "monitor" / "rib",
    }
    shim_paths = {
        "networkManagerPluginBindings.pyi": environment.prism_rib_home / "networkManagerPluginBindings.pyi",
    }

    android_docker_base = Path("/code/android/out/")


class Build(ExternalCommand):
    """Build the latest artifacts."""

    aliases = ["b"]
    rebuild_libs: bool = False
    extract_shims: bool = False
    android: bool = False

    def run(self):
        if self.rebuild_libs:
            self.docker_build(prt_docker_image, prt_dockerfile)
        self.copy_artifacts()

        if self.android:
            self.build_android()

    def docker_build(self, image, dockerfile, **build_args):
        cmd = [
            "docker",
            "build",
            "-t",
            image,
            "-f",
            dockerfile,
            "--build-arg",
            f"RACE_VERSION={environment.race_version}",
        ]

        for k, v in build_args.items():
            cmd.extend(["--build-arg", f"{k.upper()}={v}"])

        cmd.append(".")

        env = {"DOCKER_BUILDKIT": "1"}
        result = self.subprocess(cmd, cwd=environment.repo_home, env=env, capture_output=not self.verbose)
        if result.returncode:
            raise PRTError("Docker build failed.")

    def copy_artifacts(self):
        if release_path.exists():
            shutil.rmtree(release_path)
        release_path.mkdir()

        for path_name in source_paths.keys():
            source = source_paths[path_name]
            dest = release_paths[path_name]
            dest.parent.mkdir(parents=True, exist_ok=True)

            if source.is_dir():
                shutil.copytree(
                    source, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store")
                )
            else:
                shutil.copy(source, dest)

        for path_name in prebuilt_paths.keys():
            source = prebuilt_paths[path_name]
            if path_name in release_paths:
                dest = release_paths[path_name]
            else:
                printf(f"No release path found for {path_name}")
                continue
            
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source, dest)

        if self.rebuild_libs:
            with self.docker_mount(prt_docker_image) as pull:
                for path_name in docker_source_paths.keys():
                    source = docker_source_paths[path_name]

                    if path_name in release_paths:
                        dest = release_paths[path_name]
                    elif path_name in shim_paths:
                        if not self.extract_shims:
                            continue
                        dest = shim_paths[path_name]
                    else:
                        print(f"Could not find output path for {path_name} from Docker image.")
                        continue

                    dest.parent.mkdir(parents=True, exist_ok=True)
                    pull(source, dest)
                    

 
    def build_android(self):
        self.docker_build(prt_android_image, prt_android_dockerfile)

        with self.docker_mount(prt_android_image) as pull:
            for arch in ["x86_64", "arm64-v8a"]:
                dest = artifacts_path / f"android-{arch}-client" / "prism"
                dest.parent.mkdir(exist_ok=True, parents=True)
                source = android_docker_base / arch / "artifacts" / "prism"
                pull(source, dest)

    @contextmanager
    def docker_mount(self, image: str):
        container = None
        try:
            container = self.subprocess(["docker", "create", image], capture_output=True).stdout.decode("utf-8").strip()

            def pull(container_path: Path, local_path: Path):
                cmd = ["docker", "cp", f"{container}:{container_path}", local_path]
                self.subprocess(cmd, capture_output=True)

            yield pull
        finally:
            if container:
                self.subprocess(["docker", "rm", container], capture_output=True)

    @classmethod
    def extend_parser(cls, parser: ArgumentParser):
        parser.add_argument(
            "--rebuild-libs", action="store_true", help="Rebuilt a new version of bfibe"
        )
        parser.add_argument("--android", action="store_true", help="Build artifacts for Android")
        parser.add_argument(
            "--extract-shims",
            action="store_true",
            help="Extract the latest version of the RACE SDK shims for "
                 "from the prt-rib-artifacts docker image."
        )
