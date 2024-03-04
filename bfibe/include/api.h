/*
 * Copyright (c) 2019-2020 SRI International.
 * All rights reserved.
 */

/*
** Generate a new IBE system at the given security level. Fills in pointers to the system parameters and the system secret.
** Security level is between 1 and 5, and should be at least 3 in production. More details in src/security.c.
*/
void generate_system(int security_level, void** system_out, void**secret_out);

/*
** Generate a new IBE shard for an existing system, with the same parameters except
** for the secret s and the public parameter P_pub.
*/
void generate_shard(void *base_system, void **system_out, void **secret_out);

/*
** Utilities for converting secret keys to and from strings.
*/
char *format_system_secret(void* secret);
void *parse_system_secret(const char* secret_string);

/*
** Utilities for converting system params to and from strings.
*/
char *format_system_params(void* system);
void *parse_system_params(const char* param_string);

/*
** Utilities for generating and loading private keys.
*/
char *generate_private_key(void* system, void* secret, char* address);
char *format_private_key(void *private_key);
void *parse_private_key(void *system, const char* key_string);

/*
** The encryption and decryption functions.
*/
void *encrypt_ibe(void *system, char* address, void *message, int message_len, int* out_length);
void *decrypt_ibe(void *system, void *key, void *ciphertext, int ciphertext_len, int* out_length);

/*
** Functions for combining IBE shards.
*/
void *add_public(void *system1, void *system2);
char *add_secret(void *system, char *secret1, char *secret2);
