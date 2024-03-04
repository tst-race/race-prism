#!/usr/bin/env bash
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

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
SRC_DIR="$SCRIPT_DIR/src"
pushd "$SCRIPT_DIR"
source versions.sh
mkdir -p "$SRC_DIR"
pushd "$SRC_DIR"


wget https://www.openssl.org/source/openssl-$OPENSSL_VERSION.tar.gz
wget https://crypto.stanford.edu/pbc/files/pbc-$PBC_VERSION.tar.gz
# wget https://gmplib.org/download/gmp/gmp-$GMP_VERSION.tar.xz
tar xf openssl*.tar*
# tar xf gmp*.tar*
tar xf pbc*.tar*
rm *.tar.*
