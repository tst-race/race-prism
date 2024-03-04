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

export PROJECT=gmp
source buildenv.sh
source versions.sh

export GMP_DIR=gmp-$GMP_VERSION

pushd $BASE_DIR/src

pushd $GMP_DIR
if [[ -e Makefile ]]; then
make clean
fi

echo ./configure --enable-silent-rules --host ${TARGET_ARCH}-linux-android${EABI} --enable-cxx
./configure --enable-silent-rules --host ${TARGET_ARCH}-linux-android${EABI} --enable-cxx
echo make -j$MAKE_JOBS
make -j$MAKE_JOBS
popd

echo cp $GMP_DIR/.libs/libgmp*.[s]* $LIB_DIR/
cp $GMP_DIR/.libs/libgmp*.[s]* $LIB_DIR/
echo cp $GMP_DIR/gmp.h $GMP_DIR/gmpxx.h $INCLUDE_DIR/
cp $GMP_DIR/gmp.h $GMP_DIR/gmpxx.h $INCLUDE_DIR/


popd
