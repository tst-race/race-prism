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

export PROJECT=bfibe
source buildenv.sh

IBE_DIR=$BASE_DIR/src/bfibe

pushd $BASE_DIR
rm -rf $BUILD_DIR/bfibe
mkdir $BUILD_DIR/bfibe
pushd $BUILD_DIR/bfibe

${CMAKE} -G"Unix Makefiles" \
         -DANDROID_ABI=${CMAKE_TARGET_ARCH} \
         -DANDROID_PLATFORM=android-${TARGET_API} \
         -DANDROID_TOOLCHAIN=${COMPILER} \
         -DCMAKE_TOOLCHAIN_FILE=${NDK_ROOT}/build/cmake/android.toolchain.cmake \
         -DCMAKE_FIND_ROOT_PATH_MODE_LIBRARY=BOTH \
         -DCMAKE_FIND_ROOT_PATH_MODE_INCLUDE=BOTH \
         -DCMAKE_LIBRARY_PATH=$LIB_DIR \
         -DCMAKE_INCLUDE_PATH=$INCLUDE_DIR \
         -DOPENSSL_ROOT_DIR=$BASE_DIR \
         $IBE_DIR
make -j${MAKE_JOBS}
popd

cp $BUILD_DIR/bfibe/lib*.[s]* $LIB_DIR/
cp $IBE_DIR/include/*.h $INCLUDE_DIR/

popd
