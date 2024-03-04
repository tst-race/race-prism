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

vfile = Path(__file__).parent / "VERSION"
VERSION = vfile.read_text().strip()

setup(
    name='prism',
    version=VERSION,
    scripts=["bin/prism"],
    packages=find_packages(include=['prism', 'prism.*'])
)
