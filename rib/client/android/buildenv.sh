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

if [[ -z ${SDK_ROOT-} ]]; then
    export SDK_ROOT=/opt/android
fi

if [[ -z ${NDK_ROOT-} ]]; then
    export NDK_ROOT=$SDK_ROOT/ndk/default
fi

# For OpenSSL
export ANDROID_NDK_HOME=$NDK_ROOT

if [[ -z ${HOST_ARCH-} ]]; then
    export HOST_ARCH=linux-x86_64
fi

# Valid options: x86_64, i686, aarch64, arm
if [[ -z ${TARGET_ARCH-} ]]; then
    export TARGET_ARCH=x86_64
fi

if [[ -z ${TARGET_API-} ]]; then
    export TARGET_API=29
fi

if [[ -z ${MAKE_JOBS-} ]]; then
    export MAKE_JOBS=12
fi

# Common paths
export BASE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
export BUILD_DIR=$BASE_DIR/build
export INCLUDE_DIR=$BASE_DIR/include
export LIB_DIR=$BASE_DIR/lib/$TARGET_ARCH

# Cmake parameters
export COMPILER=clang

if [[ -z ${CMAKE-} ]]; then
    export CMAKE=cmake
fi

export EABI=""

case $TARGET_ARCH in
    aarch64)
        export CMAKE_TARGET_ARCH=arm64-v8a
        export LIB_DIR=$BASE_DIR/lib/arm64-v8a
        export OUT_ARCH=arm64-v8a
        ;;
    *)
        export CMAKE_TARGET_ARCH=$TARGET_ARCH
        export OUT_ARCH=$TARGET_ARCH
esac

mkdir -p $BUILD_DIR
mkdir -p $INCLUDE_DIR
mkdir -p $LIB_DIR

# Automake parameters
export TOOLCHAIN=${NDK_ROOT}/toolchains/llvm/prebuilt/${HOST_ARCH}
# export AR=${TOOLCHAIN}/bin/${TARGET_ARCH}-linux-android${EABI-}-ar
export AS=${TOOLCHAIN}/bin/${TARGET_ARCH}-linux-android${EABI-}-as
export CC=${TOOLCHAIN}/bin/${TARGET_ARCH}${ARMV-}-linux-android${EABI-}${TARGET_API}-clang
export CXX=${TOOLCHAIN}/bin/${TARGET_ARCH}${ARMV-}-linux-android${EABI-}${TARGET_API}-clang++
export LD=${TOOLCHAIN}/bin/${TARGET_ARCH}-linux-android${EABI-}-ld
export RANLIB=${TOOLCHAIN}/bin/llvm-ranlib
# export RANLIB=${TOOLCHAIN}/bin/${TARGET_ARCH}-linux-android${EABI-}-ranlib
export STRIP=${TOOLCHAIN}/bin/${TARGET_ARCH}-linux-android${EABI-}-strip

export CPPFLAGS="-I${INCLUDE_DIR} -g"
export LDFLAGS="-L${LIB_DIR}"
