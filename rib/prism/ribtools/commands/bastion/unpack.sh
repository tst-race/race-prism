#!/bin/bash
#
# Copyright (c) 2019-2023 SRI International.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
set -euo pipefail

# Script that executes on a node to unpack the release tarball and apply hotfixes.
tar xzf release.tgz

if [[ `hostname` =~ client ]]; then
  cp -r release/artifacts/linux-x86_64-client/prism /usr/local/lib/race/network-manager/
fi

if [[ `hostname` =~ server ]]; then
  cp -r release/artifacts/linux-x86_64-server/prism /usr/local/lib/race/network-manager/
fi
