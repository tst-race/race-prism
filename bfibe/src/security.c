/*
 * Copyright (c) 2019-2020 SRI International.
 * All rights reserved.
 */

#include "security.h"
#include <openssl/sha.h>

/*
 * Sets the relevant security parameters based on a specified
 * level of desired security (between 1 and 5). 3 is probably
 * the minimum that you should use. 1 and 2 are there for
 * the sake of completely implementing the RFC.
 *
 * Returns false if an invalid security level is requested.
 */
bool setup_security(BFSecurityLevel *security, uint8_t level) {
  security->level = level;

  switch (level) {
  case 1:
    security->n_p = 512;
    security->n_q = 160;
    security->hashlen = SHA_DIGEST_LENGTH;
    security->hashfcn = SHA1;
    break;
  case 2:
    security->n_p = 1024;
    security->n_q = 224;
    security->hashlen = SHA224_DIGEST_LENGTH;
    security->hashfcn = SHA224;
    break;
  case 3:
    security->n_p = 1536;
    security->n_q = 256;
    security->hashlen = SHA256_DIGEST_LENGTH;
    security->hashfcn = SHA256;
    break;
  case 4:
    security->n_p = 3840;
    security->n_q = 384;
    security->hashlen = SHA384_DIGEST_LENGTH;
    security->hashfcn = SHA384;
    break;
  case 5:
    security->n_p = 7680;
    security->n_q = 512;
    security->hashlen = SHA512_DIGEST_LENGTH;
    security->hashfcn = SHA512;
    break;
  default:
    return false;
  }

  return true;
}
