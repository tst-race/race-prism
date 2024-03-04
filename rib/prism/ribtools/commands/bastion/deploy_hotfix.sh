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

# Script used by hotfix.py to deploy hotfixes to AWS/T&E nodes.
# Takes as arguments the list of nodes to hotfix.

SSHOPTS="-q -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

deploy_to_node() {
  scp $SSHOPTS ~/release.tgz ./unpack.sh $1:
  ssh $SSHOPTS $1 bash unpack.sh
}

for node in "$@"; do
  deploy_to_node $node &
done

wait