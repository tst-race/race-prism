/*
 * Copyright (c) 2019-2020 SRI International.
 * All rights reserved.
 */

#include "bfibe.h"
#include <string.h>
#include <time.h>
#include <openssl/rand.h>

// 256-bit AES key
const int PAYLOAD_BYTES = 32;
const int REPS = 100;
char *EMAIL = "alice@example.com";

double benchmark_paramgen(BFPublicParameters *params, mpz_t s, uint8_t level) {
  clock_t start, end;

  start = clock();
  bf_setup(params, s, level);
  end = clock();

  return ((double) end - start) / (double) CLOCKS_PER_SEC;
}

int main() {
  double init_times[5] = {0.0};
  double encrypt_times[5] = {0.0};
  double decrypt_times[5] = {0.0};

  // Generate test data to encrypt
  uint8_t aes_key[PAYLOAD_BYTES];
  uint8_t decrypted_key[PAYLOAD_BYTES];
  RAND_bytes(aes_key, PAYLOAD_BYTES);

  // Initialize each security level
  BFPublicParameters params[5];
  mpz_t s[5];
  for(uint8_t i = 0; i < 5; i++) {
    mpz_init(s[i]);
    init_times[i] = benchmark_paramgen(&params[i], s[i], i+1);
  }

  for(uint8_t i = 0; i < 5; i++) {
    // Generate Alice's public key
    element_t alicePub;
    element_init_G2(alicePub, params[i].pairing);
    bf_generate_public_key(alicePub, &params[i], EMAIL);

    // Generate Alice's private key.
    element_t alicePK;
    element_init_G2(alicePK, params[i].pairing);
    bf_generate_private_key(alicePK, &params[i], s[i], EMAIL);

    // Benchmark encryption
    clock_t start = clock();
    for(int j = 0; j < REPS; j++) {
      BFMessage *encryptedMessage =
        bf_encrypt(&params[i], alicePub, aes_key, PAYLOAD_BYTES);
      free(encryptedMessage);
    }
    clock_t end = clock();
    encrypt_times[i] = ((double)end - start) / (double)CLOCKS_PER_SEC / (double)REPS;

    // Encrypt a message for Alice
    BFMessage *encryptedMessage =
      bf_encrypt(&params[i], alicePub, aes_key, PAYLOAD_BYTES);

    start = clock();
    // Decrypt the message
    for(int j = 0; j < REPS; j++) {
      bf_decrypt(decrypted_key, &params[i], alicePK, encryptedMessage);
    }
    end = clock();
    decrypt_times[i] = ((double)end - start) / (double)CLOCKS_PER_SEC / (double)REPS;

    free(encryptedMessage);
    element_clear(alicePub);
    element_clear(alicePK);
  }

  for(int i = 0; i < 5; i++) {
    printf("Security level %d\nModulus bits: %d\nHash bits: %d\n"
           "Initialize: %f\nEncrypt: %f\nDecrypt: %f\n\n",
           i+1, params[i].security.n_p, params[i].security.n_q,
           init_times[i], encrypt_times[i], decrypt_times[i]);
  }

  return 0;
}
