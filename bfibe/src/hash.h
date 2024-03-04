/*
 * Copyright (c) 2019-2020 SRI International.
 * All rights reserved.
 */

#pragma once

/*
 * Hash arbitrary data into a point on the curve defined by params.
 */
void hash_to_point(element_t Q, BFPublicParameters *params, void *input,
                   size_t len);

/*
 * Hash arbitrary data into an integer between 0 and q-1 (inclusive)
 */
void hash_to_range(mpz_t result, BFPublicParameters *params, void *input,
                   size_t len, mpz_t q);

/*
 * Hash arbitrary input data into outlen random bytes.
 */
void hash_to_bytes(uint8_t *result, BFPublicParameters *params, size_t outlen,
                   void *input, size_t len);
