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
from dynaconf import Dynaconf
import json
from pathlib import Path
import pkg_resources
import structlog
from typing import List, Optional

from prism.common.config.watchdog import Watchdog

CONFIG_LOGGER = structlog.getLogger("prism.common.config")


def module_config_path(file_name: str) -> Optional[Path]:
    try:
        return Path(pkg_resources.resource_filename(__package__, file_name))
    except:
        return None


config_files = [
    module_config_path("common.toml"),
    module_config_path("client.toml"),
    module_config_path("server.toml")
]

configuration = Dynaconf(
    envvar_prefix="PRISM",
    settings_files=config_files,
)


def init_config(config_json: Optional[str], files: List[Path]):
    """
    Initialize and configure a PRISM object.  If no arguments are given, the configuration will use the
    default values plus overriding with any environment variables that are prefixed by PRISM_.  However,
    you can only use environment variables with PRISM_ for settings that are not loaded using this function.

    If additional arguments are given, then these configurations augment and possibly override the default.
    If both arguments are present, then the JSON string is applied first and any keys present in both, the JSON
    string and any configuration file, will be overridden by the settings in the given files.

    If the given configuration file is a list of strings, then apply each one in their order, meaning that
    configuration keys present in multiple files (and also possibly in the default settings as well as any JSON
    string given) will be overridden with the value in the last file that contains this key.

    """
    # override any settings from arguments: first JSON, second file(s)
    if config_json is not None:
        load_json_config(config_json)

    for config_file in files:
        if not config_file.exists():
            CONFIG_LOGGER.warning(f'Cannot read configuration file at {config_file}')
        else:
            config_files.append(config_file)
            configuration.load_file(path=config_file.absolute(), silent=False)


def init_watchdog() -> Watchdog:
    """
    Return a Watchdog object that can be used to Monitor config files for changes and reload as needed at runtime.
    This may only affect certain settings that are pulled anew at runtime, e.g., to change the ARK'ing frequency
    simply edit a configuration file to include (e.g., if that was in JSON format):
    {
      "cs2_ark_timeout": 0.5,
    }
    to change the frequency to 30 seconds, which will take effect after the next ARK is sent.

    """
    return Watchdog(configuration, config_files)


def load_json_config(config_json: str):
    json_dict = None
    try:
        json_dict = json.loads(config_json)
    except json.JSONDecodeError as e:
        CONFIG_LOGGER.error(f"Could not decode given JSON string '{config_json}': {e}")

    if json_dict:  # run outside of try-except block in case that the call to load_file() throws above exception
        CONFIG_LOGGER.debug(f'Overriding configuration with settings from JSON string "{config_json}"')
        load_dict_config(json_dict)


def load_dict_config(config_dict: dict):
    upcase_dict = {k.upper(): v for k, v in config_dict.items()}
    configuration.update(upcase_dict)


def dump_config(logger):
    logger.debug("Configuration:")
    for k, v in configuration.as_dict().items():
        logger.debug(f"  {k}: {v}")
