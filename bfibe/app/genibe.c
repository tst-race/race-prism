/*
 * Copyright (c) 2019-2020 SRI International.
 * All rights reserved.
 */

#include "bfibe.h"
#include <string.h>
#include <inttypes.h>

int main(int argc, char** argv) {
  uint8_t security = 3;

  if (argc > 1) {
    sscanf(argv[1], "%" SCNu8, &security);
  }

  // Set up the cryptosystem.
  BFPublicParameters params;
  mpz_t s;
  mpz_init(s);
  bf_setup(&params, s, security);

  // Export it to files
  FILE *param_file = fopen("param.txt", "w");
  bf_params_to_file(param_file, &params);
  fclose(param_file);

  FILE *secret_file = fopen("secret.txt", "w");
  mpz_out_str(secret_file, 36, s);
  fclose(secret_file);

  return 0;
}
