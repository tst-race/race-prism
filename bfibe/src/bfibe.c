/*
 * Copyright (c) 2019-2020 SRI International.
 * All rights reserved.
 */

#include "bfibe.h"
#include "hash.h"
#include "security.h"
#include <openssl/rand.h>
#include <string.h>

/**
 * Implements the Boneh-Franklin Identity Based Encryption scheme
 * Based on the algorithms described in RFC 5091 by Voltage Security Inc.
 * https://tools.ietf.org/html/rfc5091
 *
 * The only way in which we diverge from the RFC is by using the
 * Pairing-Based Crypto library instead of manually implementing
 * the elliptic curve calculations, and as a result using the Weil
 * pairing instead of the Tate pairing.
 */

/* Redefine a PBC struct.
 * Needed to peek in and grab h for computing
 * the public parameters.
 */
typedef struct {
  int exp2;
  int exp1;
  int sign1;
  int sign0;

  // corresponds to q in rfc
  mpz_t r;
  // corresponds to p in rfc
  mpz_t q;
  // corresponds to r * 12 in rfc
  mpz_t h;
} * a_param_ptr;

/*
 * Implements the BFsetup1 algorithm
 */
bool bf_setup(BFPublicParameters *params, mpz_t s, uint8_t security_level) {
  // Step 1 omitted.

  // Step 2. Setup security parameters.
  if (!setup_security(&(params->security), security_level)) {
    return false;
  }

  // Step 3. Generate the curve and pairing
  pbc_param_init_a_gen(params->pbc_par, params->security.n_q,
                       params->security.n_p);
  pairing_init_pbc_param(params->pairing, params->pbc_par);

  // Extract parameters relevant to encryption/decryption
  a_param_ptr sp = params->pbc_par->data;
  mpz_init_set(params->q, sp->r);

  // Step 4. Find a suitable generator of F_p
  element_init_G1(params->P, params->pairing);
  do {
    element_random(params->P);
    element_mul_mpz(params->P, params->P, sp->h);
  } while (element_is0(params->P));

  // Steps 5+ are split off because this part can be used independently
  // to generate additional system secrets for other key management shards.
  bf_generate_shard(params, s);

  return true;
}

/*
** Refresh the given public parameters with a new secret and P_pub.
*/
void bf_generate_shard(BFPublicParameters *params, mpz_t s) {
  // Step 5. Generate s between 2 and q - 1
  mpz_t smax;
  mpz_init(smax);
  mpz_sub_ui(smax, params->q, 2);
  pbc_mpz_random(s, smax);
  mpz_add_ui(s, s, 2);
  mpz_clear(smax);

  // Generate the public parameter P_pub = [s]P
  element_init_same_as(params->P_pub, params->P);
  element_mul_mpz(params->P_pub, params->P, s);

  // Precompute information needed to pair with P_pub, used in encryption
  pairing_pp_init(params->P_pub_precomp, params->P_pub, params->pairing);
}

/*
 * Generate a public key from an identifier.
 */
void bf_generate_public_key(element_t public_key, BFPublicParameters *params,
                            char *identifier) {
  hash_to_point(public_key, params, identifier, strlen(identifier));
}

/*
 * Generate a private key from an identifier and the master secret.
 */
void bf_generate_private_key(element_t private_key, BFPublicParameters *params,
                             mpz_t s, char *identifier) {
  hash_to_point(private_key, params, identifier, strlen(identifier));
  element_mul_mpz(private_key, private_key, s);
}

BFMessage *bf_encrypt(BFPublicParameters *params, element_t public_key,
                      uint8_t *m, size_t len) {
  BFMessage *message = calloc(1, sizeof(*message));
  message->length = len;

  // Step 1
  size_t hlen = params->security.hashlen;
  HashFn hashfcn = params->security.hashfcn;

  // Step 2 is done for us

  // Step 3
  uint8_t rho[hlen];
  if (!RAND_bytes(rho, hlen)) {
    return NULL;
  }

  // Step 4
  uint8_t t[hlen];
  hashfcn(m, len, t);

  // Step 5
  mpz_t l;
  mpz_init(l);
  uint8_t rho_t[2 * hlen];
  memcpy(rho_t, rho, hlen);
  memcpy(rho_t + hlen, t, hlen);
  hash_to_range(l, params, rho_t, hlen + hlen, params->q);

  // Step 6
  element_init_same_as(message->U, params->P);
  element_mul_mpz(message->U, params->P, l);

  // Steps 7/8
  element_t theta;
  element_init_GT(theta, params->pairing);
  pairing_pp_apply(theta, public_key, params->P_pub_precomp);
  element_pow_mpz(theta, theta, l);

  // Step 9
  size_t zlen = element_length_in_bytes(theta);
  uint8_t z[zlen];
  element_to_bytes(z, theta);

  // Steps 10-11
  message->V = calloc(hlen, sizeof(uint8_t));
  hashfcn(z, zlen, message->V);
  for (size_t i = 0; i < hlen; i++) {
    message->V[i] = message->V[i] ^ rho[i];
  }

  // Step 12
  message->W = calloc(len, sizeof(uint8_t));
  hash_to_bytes(message->W, params, len, rho, hlen);
  for (size_t i = 0; i < len; i++) {
    message->W[i] = message->W[i] ^ m[i];
  }

  element_clear(theta);
  mpz_clear(l);

  return message;
}

bool bf_decrypt(uint8_t *output, BFPublicParameters *params,
                element_t private_key, BFMessage *message) {
  // Step 1
  size_t hlen = params->security.hashlen;
  HashFn hashfcn = params->security.hashfcn;
  bool retval = true;

  // Step 2
  element_t theta;
  element_init_GT(theta, params->pairing);
  element_pairing(theta, message->U, private_key);

  // Step 3
  size_t zlen = element_length_in_bytes(theta);
  uint8_t z[zlen];
  element_to_bytes(z, theta);

  // Step 4
  uint8_t w[hlen];
  hashfcn(z, zlen, w);

  // Step 5
  // w becomes rho
  for (size_t i = 0; i < hlen; i++) {
    w[i] = w[i] ^ message->V[i];
  }

  // Step 6
  hash_to_bytes(output, params, message->length, w, hlen);
  for (size_t i = 0; i < message->length; i++) {
    output[i] = output[i] ^ message->W[i];
  }

  // Step 7
  uint8_t t[hlen];
  hashfcn(output, message->length, t);

  // Step 8
  uint8_t rho_t[hlen * 2];
  memcpy(rho_t, w, hlen);
  memcpy(rho_t + hlen, t, hlen);

  mpz_t l;
  mpz_init(l);
  hash_to_range(l, params, rho_t, hlen * 2, params->q);

  // Step 9. Verify correctness.
  element_t lP;
  element_init_G1(lP, params->pairing);
  element_mul_mpz(lP, params->P, l);

  // Check that U = l[P]
  if (element_cmp(message->U, lP)) {
    // Check failed
    retval = false;
    memset(output, 0, message->length);
  }

  element_clear(theta);
  element_clear(lP);
  mpz_clear(l);
  return retval;
}

/* Frees the memory allocated for a message. */
void bf_message_free(BFMessage *msg) {
  free(msg->V);
  free(msg->W);
  free(msg);
}
