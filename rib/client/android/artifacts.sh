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

export TARGET_ARCH=$1

source versions.sh
source buildenv.sh

ANDROID_SUFFIX=-ANDROID-$TARGET_ARCH

INCLUDE_DIR=include
OUT_DIR=out/$OUT_ARCH
TEST_DIR=$OUT_DIR/test
ARTIFACT_DIR=$OUT_DIR/artifacts
THIRDPARTY_DIR=$OUT_DIR/3rdparty

pushd $LIB_DIR
patchelf --set-rpath '$ORIGIN/.' *.so
ln -s libpbc.so libpbc.so.1
popd

mkdir -p $TEST_DIR
mkdir -p $ARTIFACT_DIR
mkdir -p $THIRDPARTY_DIR/gmp-$GMP_VERSION$ANDROID_SUFFIX/{include,lib}
mkdir -p $THIRDPARTY_DIR/pbc-$PBC_VERSION$ANDROID_SUFFIX/{include,lib}
mkdir -p $THIRDPARTY_DIR/openssl-$OPENSSL_VERSION$ANDROID_SUFFIX/{include,lib}

cp -r prism $ARTIFACT_DIR/prism
cp $LIB_DIR/* $ARTIFACT_DIR/prism/common/crypto/ibe/

cp $LIB_DIR/*gmp* $THIRDPARTY_DIR/gmp-$GMP_VERSION$ANDROID_SUFFIX/lib/
cp $INCLUDE_DIR/gmp* $THIRDPARTY_DIR/gmp-$GMP_VERSION$ANDROID_SUFFIX/include/

cp $LIB_DIR/*pbc* $THIRDPARTY_DIR/pbc-$PBC_VERSION$ANDROID_SUFFIX/lib/
cp -r $INCLUDE_DIR/pbc $THIRDPARTY_DIR/pbc-$PBC_VERSION$ANDROID_SUFFIX/include/

cp $LIB_DIR/*crypto* $THIRDPARTY_DIR/openssl-$OPENSSL_VERSION$ANDROID_SUFFIX/lib/
cp -r $INCLUDE_DIR/openssl $THIRDPARTY_DIR/openssl-$OPENSSL_VERSION$ANDROID_SUFFIX/include/
