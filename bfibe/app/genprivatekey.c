/*
 * Copyright (c) 2019-2020 SRI International.
 * All rights reserved.
 */

#include "bfibe.h"
#include <string.h>
#include <time.h>

int main(int argc, char** argv) {
  if (argc != 2) {
    printf("Usage: %s IDENTIFIER", argv[0]);
  }

  // Read system parameters from file
  BFPublicParameters params;
  FILE *param_file = fopen("param.txt", "r");
  if(!bf_params_from_file(param_file, &params)) {
    printf("Failed to load params.\n");
    return 1;
  }
  fclose(param_file);

  mpz_t secret;
  mpz_init(secret);
  FILE *secret_file = fopen("secret.txt", "r");
  if(!mpz_inp_str(secret, secret_file, 36)) {
    printf("Failed to read secret key.\n");
    return 1;
  }

  element_t privateKey;
  element_init_G2(privateKey, params.pairing);
  bf_generate_private_key(privateKey, &params, secret, argv[1]);
  element_printf("%s\n%B\n", argv[1], privateKey);

  return 0;
}
