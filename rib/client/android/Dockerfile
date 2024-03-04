ARG RACE_CONTAINER="ghcr.io/tst-race/race-images/race-compile"
ARG RACE_VERSION

FROM ${RACE_CONTAINER}:${RACE_VERSION} AS build

# Additional dependencies for compiling Prism's dependencies
RUN apt-get update -y && \
    apt-get install -y \
        bison=2:3.5.1+dfsg-1 \
        byacc=20140715-1build1 \
        flex=2.6.4-6.2 \
        m4=1.4.* \
        patchelf=0.10-2build1 \
        texinfo

# # Switch NDK versions for compiling Prism's dependencies
ARG ANDROID_NDK_VERSION=21.4.7075529
RUN rm /opt/android/ndk/default && rm -r /opt/android/ndk/23.2.8568313
RUN yes | /opt/android/cmdline-tools/tools/bin/sdkmanager --licenses && \
    /opt/android/cmdline-tools/tools/bin/sdkmanager --install "ndk;${ANDROID_NDK_VERSION}" && \
    ln -s /opt/android/ndk/${ANDROID_NDK_VERSION} /opt/android/ndk/default


RUN apt-get update && apt-get install -y flex bison --no-install-recommends

RUN mkdir -p /code/android
WORKDIR /code/android
COPY rib/client/android/download.sh rib/client/android/versions.sh /code/android/
COPY rib/client/android/src /code/android/src
RUN bash download.sh

COPY rib/client/android/build*.sh /code/android/
COPY ./bfibe /code/android/src/bfibe

RUN bash build_all.sh x86_64
RUN bash build_all.sh aarch64

COPY prism /code/android/prism
COPY rib/prism/rib /code/android/prism/rib
COPY rib/manifests/client.json /code/android/prism/manifest.json

COPY rib/client/android/artifacts.sh /code/android
RUN bash artifacts.sh x86_64
RUN bash artifacts.sh aarch64
