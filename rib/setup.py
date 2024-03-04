#!/usr/bin/env python3
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

from setuptools import setup, find_packages
from pathlib import Path
import os

try:
    project_root = next(p for p in Path(__file__).parents
                        if p.joinpath('VERSION').exists())
    VERSION = project_root.joinpath('VERSION').read_text().strip()
except StopIteration:
    VERSION = os.environ.get('PRISM_VERSION', 'unknown')

setup(
    name='prism-rib',
    version=VERSION,
    scripts=["bin/prt"],
    packages=find_packages(include=['prism', 'prism.*'])
)
