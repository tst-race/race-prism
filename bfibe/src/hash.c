/*
 * Copyright (c) 2019-2020 SRI International.
 * All rights reserved.
 */

#include "bfibe.h"
#include <openssl/sha.h>
#include <string.h>

/*
 * Hashes to a point on the curve defined by params.
 * Q should be an initialized element of G2
 */
void hash_to_point(element_t Q, BFPublicParameters *params, void *input,
                   size_t len) {
  uint8_t *bytes = input;
  size_t hlen = params->security.hashlen;
  uint8_t md[hlen];
  params->security.hashfcn(bytes, len, md);
  element_from_hash(Q, md, hlen);
}

/*
 * Implements HashToRange from RFC 5091.
 * Hashes to an integer between 0 and q-1
 */
void hash_to_range(mpz_t result, BFPublicParameters *params, void *input,
                   size_t len, mpz_t q) {
  uint8_t *bytes = input;
  size_t hlen = params->security.hashlen;
  HashFn hashfcn = params->security.hashfcn;

  size_t tlen = (hlen + len);
  uint8_t h[hlen];
  uint8_t t[tlen];
  memset(h, 0, hlen);

  mpz_t v, vmul, a;
  mpz_inits(v, vmul, a, NULL);
  mpz_set_ui(v, 0);
  mpz_set_ui(vmul, 256);
  mpz_pow_ui(vmul, vmul, hlen);

  for (uint8_t i = 0; i < 2; i++) {
    memcpy(t, h, hlen);
    memcpy(t + hlen, bytes, len);
    hashfcn(t, tlen, h);
    mpz_import(a, hlen, 1, sizeof(h[0]), 0, 0, h);
    mpz_mul(v, v, vmul);
    mpz_add(v, v, a);
  }

  mpz_mod(result, v, q);
  mpz_clears(v, vmul, a, NULL);
}

/*
 * Implements HashBytes (4.2.1) from RFC 5091.
 * Generates outputlen random bytes based on a seed.
 */
void hash_to_bytes(uint8_t *result, BFPublicParameters *params, size_t outlen,
                   void *input, size_t len) {
  uint8_t *seed = input;
  size_t hlen = params->security.hashlen;
  HashFn hashfcn = params->security.hashfcn;

  size_t remaining = outlen;
  size_t copied = 0;

  uint8_t K[hlen];
  hashfcn(seed, len, K);

  uint8_t h[hlen];
  memset(h, 0, hlen);

  uint8_t r[hlen];
  uint8_t h_K[2 * hlen];

  while (remaining) {
    // TODO -- is it safe to pass an OpenSSL SHA function
    // the same pointer as md and d?
    hashfcn(h, hlen, h);
    memcpy(h_K, h, hlen);
    memcpy(h_K + hlen, K, hlen);
    hashfcn(h_K, 2 * hlen, r);

    if (remaining > hlen) {
      memcpy(result + copied, r, hlen);
      copied += hlen;
      remaining -= hlen;
    } else {
      memcpy(result, r, remaining);
      copied += remaining;
      remaining = 0;
    }
  }
}
