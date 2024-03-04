# C++ Libraries For PRISM Client

This directory contains scripts for building the C++ libraries the client depends on.
It assumes that you have the Android SDK/NDK installed, and have downloaded the source files for
each of the necessary libraries into the `src` subdirectory, creating subdirectories with the
version number stripped away:

* [GMP](https://gmplib.org/): `src/gmp`
* [PBC](https://crypto.stanford.edu/pbc/download.html): `src/pbc`
* [libjpeg-turbo](https://github.com/libjpeg-turbo/libjpeg-turbo): `src/libjpeg-turbo`
* [JEL](https://github.com/SRI-CSL/jel): `src/jel`
* [OpenSSL](https://www.openssl.org/): `src/openssl`

Then run `bash build_all.sh [ARCHITECTURE]`, where `[ARCHITECTURE]` is `x86_64` or `aarch64`.

Library binaries will be written to `lib/[ARCHITECTURE]`, and header files will be copied
to `include`.

If you run into trouble, check the paths in `buildenv.sh` and make sure they correspond to paths
on your own system.
