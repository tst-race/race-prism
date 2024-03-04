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

export PROJECT=pbc
source buildenv.sh
source versions.sh

export PBC_DIR=pbc-$PBC_VERSION

pushd $BASE_DIR/src

pushd $PBC_DIR
if [[ -e Makefile ]]; then
    make clean
fi

echo BUILD_PBC
echo pwd $PWD
echo ls $(ls ../)
echo ls $(ls)

./configure --host ${TARGET_ARCH}-linux-android${EABI}
make -j$MAKE_JOBS
popd

cp -Lr $PBC_DIR/.libs/libpbc.so $LIB_DIR/
cp -r $PBC_DIR/include $INCLUDE_DIR/pbc

popd
