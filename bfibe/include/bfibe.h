/*
 * Copyright (c) 2019-2020 SRI International.
 * All rights reserved.
 */

#pragma once
#include <pbc/pbc.h>
#include <stdbool.h>

typedef uint8_t *(*HashFn)(const uint8_t *, size_t, uint8_t *);

/*
 * Stores information about security parameters.
 */
typedef struct {
  uint8_t level;

  // Corresponds to qbits in pbc. Used for order of GT
  uint32_t n_p;

  // Corresponds to rbits in pbc. Used for order of subgroup G1
  uint32_t n_q;

  // Number of bytes produced by SHA hashing algorithm
  size_t hashlen;

  HashFn hashfcn;
} BFSecurityLevel;

/*
 * Stores the public parameters of the Boneh-Franklin
 * IBE system.
 */
typedef struct {
  BFSecurityLevel security;

  // The Elliptic curve and pairing data.
  pbc_param_t pbc_par;
  pairing_t pairing;

  // The public curve elements, in G1
  element_t P, P_pub;

  // During encryption, we pair the public key of the recipient
  // with P_pub. This data structure precomputes some of that,
  // calculation to make encryption faster.
  pairing_pp_t P_pub_precomp;

  // The order of the cyclic subgroup of G1
  // Used in encryption/decryption.
  mpz_t q;
} BFPublicParameters;

/*
 * An encrypted message.
 */
typedef struct {
  // The length of the plaintext
  size_t length;

  // A member of G1
  element_t U;

  // A hash-length bag of bytes
  uint8_t *V;

  // A message-length bag of bytes
  uint8_t *W;
} BFMessage;

/*
 * Sets up a BF IBE system
 * Fills out params with the public parameters
 * Fills out s with the secret key
 *
 * Security level determines how many bits are in the primes,
 * and what hash function is used. Recommend at least level 2.
 */
bool bf_setup(BFPublicParameters *params, mpz_t s, uint8_t security_level);

/**
 * Given a set of public parameters, generate new secret key as s and
 * reset P_pub
 */
void bf_generate_shard(BFPublicParameters *params, mpz_t s);

/*
 * Generates a public key from an identity.
 * public_key should be an initialized member of G2.
 */
void bf_generate_public_key(element_t public_key, BFPublicParameters *params,
                            char *identifier);

/*
 * Generates a private key from an identity and the secret key.
 * private_key should be an initialized member of G2.
 */
void bf_generate_private_key(element_t private_key, BFPublicParameters *params,
                             mpz_t s, char *identifier);

/*
 * Allocates and encrypts a message.
 * Should only be used to encrypt session keys.
 * len should contain the length of m in bytes.
 */
BFMessage *bf_encrypt(BFPublicParameters *params, element_t public_key,
                      uint8_t *m, size_t len);

/*
 * Decrypts a message into output.
 * output should already be allocated.
 */
bool bf_decrypt(uint8_t *output, BFPublicParameters *params,
                element_t private_key, BFMessage *message);

/*
 * Export and import the public parameters to/from a file/string.
 */
void bf_params_to_file(FILE *out, BFPublicParameters *params);
bool bf_params_from_file(FILE *in, BFPublicParameters *params);
size_t bf_params_to_string(uint8_t **out, BFPublicParameters *params);
bool bf_params_from_string(uint8_t *in, BFPublicParameters *params);

/*
 * Export and import a message to/from a file/string/byte array.
 */
void bf_message_to_file(FILE *out, BFPublicParameters *params, BFMessage *msg);
bool bf_message_from_file(FILE *in, BFPublicParameters *params, BFMessage *msg);
size_t bf_message_to_string(uint8_t **out, BFPublicParameters *params,
                            BFMessage *msg);
bool bf_message_from_string(uint8_t *in, BFPublicParameters *params,
                            BFMessage *msg);
size_t bf_message_to_bytes(uint8_t **out, BFPublicParameters *params,
                           BFMessage *msg);
bool bf_message_from_bytes(uint8_t *in, BFPublicParameters *params,
                           BFMessage *msg);

void bf_message_free(BFMessage *msg);
