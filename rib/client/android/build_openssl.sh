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

export PROJECT=openssl
source buildenv.sh
source versions.sh

export OPENSSL_DIR=openssl-$OPENSSL_VERSION

pushd $BASE_DIR/src

pushd $OPENSSL_DIR
if [[ -e Makefile ]]; then
    make clean
fi

export PATH=${TOOLCHAIN}/bin:$PATH
export CC=clang

case $TARGET_ARCH in
    aarch64)
        export OPENSSL_TARGET_ARCH=android-arm64
        ;;
    x86_64)
        export OPENSSL_TARGET_ARCH=android-x86_64
        ;;
    *)
        export OPENSSL_TARGET_ARCH=android-${TARGET_ARCH}
esac

./Configure ${OPENSSL_TARGET_ARCH} -D__ANDROID_API__=${TARGET_API}
make -j$MAKE_JOBS
popd

cp $OPENSSL_DIR/libcrypto.so.1.1 $LIB_DIR/
pushd $LIB_DIR
ln -s libcrypto.so.1.1 libcrypto.so
popd
cp -r $OPENSSL_DIR/include/openssl $INCLUDE_DIR/openssl

popd
