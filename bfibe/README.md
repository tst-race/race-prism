# Boneh-Franklin IBE

Implements the Boneh-Franklin Identity-Based Encryption scheme as described in [Identity-Based Encryption from the Weil Pairing](https://crypto.stanford.edu/~dabo/papers/bfibe.pdf), and further specified in [RFC 5091](https://tools.ietf.org/html/rfc5091).

## Dependencies

* [Pairing-Based Cryptography Library](https://crypto.stanford.edu/pbc/)
* [GMP](https://gmplib.org/)
* [OpenSSL](https://www.openssl.org/)
* [Cmake](https://cmake.org/) 3.12 or greater

On a Mac, all dependencies can be installed via Homebrew, with the command

    brew install cmake pbc openssl
    brew install --cask corretto
    
You will need to use the Homebrew version of OpenSSL rather than the system OpenSSL on recent macOS releases, 
because Apple does not allow linking to the system install of OpenSSL. `corretto` is Amazon's release of OpenJDK, 
but you can use a different release if you prefer.

## Building

    mkdir build
    cd build
    cmake ..
    make
    make install

If you installed OpenSSL via Homebrew, you'll need to use

    cmake -DOPENSSL_ROOT_DIR=/usr/local/opt/openssl/ ..

or (using the hints that `brew reinstall openssl@3` gives), e.g.:

    export LDFLAGS="-L/usr/local/opt/openssl@3/lib"
    export CPPFLAGS="-I/usr/local/opt/openssl@3/include"
    export PKG_CONFIG_PATH="/usr/local/opt/openssl@3/lib/pkgconfig"
    cmake ..

instead. If you have to fix any compilation errors, you may need to delete and remake the `build` directory to clear 
out CMake's cache.

## Setting up an IBE System

Run `genibe [SECURITY_LEVEL]`, which will generate files `params.txt` and
`secret.txt` which contain the public and private parameters of the system,
respectively. The security level determines how big the parameter space is,
and how big the SHA hashes used in the algorithms are. It ranges from 1-5.

Security level 3 uses 256-bit keys and SHA-256 and should probably be
considered the minimal secure level. 4 and 5 are more secure, but
exponentially slower.

## Generating Keys

Run `genprivatekey [IDENTIFIER]` to generate a private key file to give to
a user.
