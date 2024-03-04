/*
 * Copyright (c) 2019-2020 SRI International.
 * All rights reserved.
 */

#include "api.h"
#include "bfibe.h"

const int BIGINT_STRING_BASE = 36;

BFPublicParameters *copy_params(BFPublicParameters *params) {
    char *param_str = format_system_params(params);
    BFPublicParameters *params_result = parse_system_params(param_str);
    free(param_str);
    return params_result;
}

void generate_system(int security_level, void** system_out, void**secret_out) {
    BFPublicParameters *params = calloc(1, sizeof(*params));
    mpz_t *s = calloc(1, sizeof(*s));
    mpz_init(*s);

    bf_setup(params, *s, security_level);

    *system_out = params;
    *secret_out = s;
}

void generate_shard(void *base_system, void **system_out, void **secret_out) {
    BFPublicParameters *params = (BFPublicParameters *)base_system;
    BFPublicParameters *params_out = copy_params(params);

    mpz_t *s = calloc(1, sizeof(*s));
    mpz_init(*s);

    element_clear(params_out->P_pub);
    pairing_pp_clear(params_out->P_pub_precomp);
    bf_generate_shard(params_out, *s);

    *system_out = params_out;
    *secret_out = s;
}

char *format_system_secret(void* secret) {
    mpz_t *s = (mpz_t*)secret;
    return mpz_get_str(NULL, BIGINT_STRING_BASE, *s);
}

void *parse_system_secret(const char* secret_string) {
    mpz_t *s = calloc(1, sizeof(*s));
    mpz_init(*s);
    int error = mpz_set_str(*s, secret_string, BIGINT_STRING_BASE);

    if(error) {
        return NULL;
    }

    return s;
}


/* System params */

char *format_system_params(void* system) {
    BFPublicParameters *params = (BFPublicParameters*) system;
    uint8_t **out_str = calloc(1, sizeof(out_str));
    size_t byte_count = bf_params_to_string(out_str, system);
    return (char*)(*out_str);
}

void *parse_system_params(const char* param_string) {
    BFPublicParameters *params = calloc(1, sizeof(*params));
    bf_params_from_string((uint8_t *)param_string, params);
    return params;
}


/* Private keys */

char *generate_private_key(void* system, void* secret, char* address) {
    BFPublicParameters *params = (BFPublicParameters*) system;
    mpz_t *system_secret = (mpz_t*)secret;

    element_t private_key;
    element_init_G2(private_key, params->pairing);
    bf_generate_private_key(private_key, params, *system_secret, address);

    return format_private_key(&private_key);
}

char *format_private_key(void *private_key) {
    /*
     * Create a fake buffer for the first attempt.
     * element_snprint will fail, but will return the number of bytes we need to allocate.
     * */
    char tmp_buf[8];
    int char_count = element_snprint(tmp_buf, 5, private_key) + 1;
    char *out_str = calloc(char_count, sizeof(*out_str));
    element_snprint(out_str, char_count, private_key);
    return out_str;
}

void *parse_private_key(void *system, const char* key_string) {
    BFPublicParameters *params = (BFPublicParameters *)system;
    element_t *privateKey = calloc(1, sizeof(*privateKey));
    element_init_G2(*privateKey, params->pairing);
    element_set_str(*privateKey, key_string, 10);
    return privateKey;
}


/* Encryption/decryption */

void *encrypt_ibe(void *system, char* address, void *message, int message_len, int* out_length) {
    BFPublicParameters *params = (BFPublicParameters *)system;

    element_t public_key;
    element_init_G2(public_key, params->pairing);

    bf_generate_public_key(public_key, params, address);
    BFMessage *ciphertext = bf_encrypt(params, public_key, (uint8_t*)message, message_len);

    uint8_t *cipher_bytes;
    *out_length = bf_message_to_bytes(&cipher_bytes, params, ciphertext);

    free(ciphertext->V);
    free(ciphertext->W);
    free(ciphertext);
    element_clear(public_key);

    return cipher_bytes;
}

void *decrypt_ibe(void *system, void *key, void *ciphertext, int ciphertext_len, int* out_length) {
    BFPublicParameters *params = (BFPublicParameters *)system;
    element_t* private_key = (element_t *)key;

    BFMessage msg;
    if(!bf_message_from_bytes((uint8_t*)ciphertext, params, &msg)) {
        return NULL;
    }

    uint8_t *msg_bytes = calloc(msg.length, sizeof(uint8_t));
    bf_decrypt(msg_bytes, params, *private_key, &msg);
    *out_length = msg.length;

    free(msg.V);
    free(msg.W);

    return msg_bytes;
}

void *add_public(void *system1, void *system2) {
    BFPublicParameters *params1 = (BFPublicParameters *)system1;
    BFPublicParameters *params2 = (BFPublicParameters *)system2;

    // We can only sum two public parameters using the same modulus and security level
    if ((params1->security.level != params2->security.level) || mpz_cmp(params1->q, params2->q)) {
        return NULL;
    }
    // TODO also check if we're using the same elliptic curve

    BFPublicParameters *params_result = copy_params(params1);
    pairing_pp_clear(params_result->P_pub_precomp);

    element_add(params_result->P_pub, params1->P_pub, params2->P_pub);
    pairing_pp_init(params_result->P_pub_precomp, params_result->P_pub, params_result->pairing);
    return params_result;
}

char *add_secret(void *system, char *secret1, char *secret2) {
    BFPublicParameters *params = (BFPublicParameters *)system;
    element_t *s1 = parse_private_key(params, secret1);
    element_t *s2 = parse_private_key(params, secret2);

    element_t *secret_result = calloc(1, sizeof(*secret_result));
    element_init_G2(*secret_result, params->pairing);
    element_add(*secret_result, *s1, *s2);

    element_clear(*s1);
    element_clear(*s2);
    free(s1);
    free(s2);
    char *out_str = format_private_key(secret_result);
    element_clear(*secret_result);
    free(secret_result);
    return out_str;
}
