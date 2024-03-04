/*
 * Copyright (c) 2019-2020 SRI International.
 * All rights reserved.
 */

#include "base64.h"
#include "bfibe.h"
#include "security.h"
#include <inttypes.h>
#include <string.h>
#include <stdio.h>

const int MPZ_OUTPUT_BASE = 36;
const int BUFFER_SIZE = 8192;

void bf_params_to_file(FILE *out, BFPublicParameters *params) {
  fprintf(out, "security %" PRIu8 "\n", params->security.level);
  element_fprintf(out, "%B\n%B\n", params->P, params->P_pub);
  mpz_out_str(out, MPZ_OUTPUT_BASE, params->q);
  fprintf(out, "\n");
  pbc_param_out_str(out, params->pbc_par);
}

bool bf_params_from_file(FILE *in, BFPublicParameters *params) {
  // Read security level
  uint8_t security_level;
  if (!fscanf(in, "security %" SCNu8 "\n", &security_level)) {
    printf("Failed to read security level.\n");
    return false;
  }
  setup_security(&(params->security), security_level);

  // Read elements P and P_pub
  char P_buf[BUFFER_SIZE];
  char P_pub_buf[BUFFER_SIZE];
  if (!fgets(P_buf, BUFFER_SIZE, in)) {
    printf("Failed to read P.\n");
    return false;
  }
  if (!fgets(P_pub_buf, BUFFER_SIZE, in)) {
    printf("Failed to read P_pub.\n");
    return false;
  }

  // Read q
  mpz_init(params->q);
  if (!mpz_inp_str(params->q, in, MPZ_OUTPUT_BASE)) {
    printf("Failed to read q.\n");
    return false;
  }

  // Read pbc_par
  long int current_pos = ftell(in);
  fseek(in, 0, SEEK_END);
  long int end = ftell(in);
  int param_len = end - current_pos + 1;
  fseek(in, current_pos, SEEK_SET);

  char param_buf[param_len + 1];
  size_t bytes_read = fread(param_buf, 1, param_len, in);

  if (!bytes_read) {
    printf("Failed to read pbc_par.\nparam_len: %d\n", param_len);
    mpz_clear(params->q);
    return false;
  }
  param_buf[bytes_read] = 0;

  if (pbc_param_init_set_str(params->pbc_par, param_buf)) {
    printf("Failed to parse pbc_par.\n");
    mpz_clear(params->q);
    return false;
  }
  pairing_init_pbc_param(params->pairing, params->pbc_par);

  // Initialize P and P_Pub
  element_init_G1(params->P, params->pairing);
  element_init_same_as(params->P_pub, params->P);
  if (!element_set_str(params->P, P_buf, 10)) {
    mpz_clear(params->q);
    element_clear(params->P);
    element_clear(params->P_pub);
    return false;
  }
  if (!element_set_str(params->P_pub, P_pub_buf, 10)) {
    mpz_clear(params->q);
    element_clear(params->P);
    element_clear(params->P_pub);
    return false;
  }
  pairing_pp_init(params->P_pub_precomp, params->P_pub, params->pairing);

  return true;
}

size_t bf_params_to_string(uint8_t **out, BFPublicParameters *params) {
  size_t written_bytes;
  FILE *fp = open_memstream((char **)out, &written_bytes);
  bf_params_to_file(fp, params);
  fclose(fp);
  return written_bytes;
}

bool bf_params_from_string(uint8_t *in, BFPublicParameters *params) {
  FILE *fp = fmemopen(in, strlen((char *)in), "r");
  bool retval = bf_params_from_file(fp, params);
  fclose(fp);
  return retval;
}

void bf_message_to_file(FILE *out, BFPublicParameters *params, BFMessage *msg) {
  uint8_t *str;
  bf_message_to_string(&str, params, msg);
  fprintf(out, "%s", str);
  free(str);
}

bool bf_message_from_file(FILE *in, BFPublicParameters *params,
                          BFMessage *msg) {
  fseek(in, 0, SEEK_END);
  size_t length = ftell(in);
  fseek(in, 0, SEEK_SET);

  uint8_t *buf = malloc(length + 1);
  if (!buf) {
    return false;
  }
  fread(buf, 1, length, in);
  buf[length] = 0;

  bool retval = bf_message_from_string(buf, params, msg);
  free(buf);
  return retval;
}

size_t bf_message_to_string(uint8_t **out, BFPublicParameters *params,
                            BFMessage *msg) {
  uint8_t *byteBuf;
  size_t blen = bf_message_to_bytes(&byteBuf, params, msg);
  *out = base64_encode(byteBuf, blen);
  free(byteBuf);
  return strlen((char *)*out);
}

bool bf_message_from_string(uint8_t *in, BFPublicParameters *params,
                            BFMessage *msg) {
  uint8_t *byteBuf;
  size_t blen;
  byteBuf = base64_decode(in, &blen);
  bool retval = bf_message_from_bytes(byteBuf, params, msg);
  free(byteBuf);
  return retval;
}

// FIXME: message_to_bytes and message_from_bytes probably have endian-ness
// issues
size_t bf_message_to_bytes(uint8_t **out, BFPublicParameters *params,
                           BFMessage *msg) {
  size_t size_size = sizeof(size_t);
  size_t element_size = element_length_in_bytes(msg->U);
  size_t output_size =
      size_size + 1 + element_size + params->security.hashlen + msg->length;

  *out = malloc(output_size);
  uint8_t *writeptr = *out;

  memcpy(writeptr, &(msg->length), size_size);
  writeptr += size_size;

  *writeptr = params->security.level;
  writeptr++;

  writeptr += element_to_bytes(writeptr, msg->U);

  memcpy(writeptr, msg->V, params->security.hashlen);
  writeptr += params->security.hashlen;

  memcpy(writeptr, msg->W, msg->length);

  return output_size;
}

bool bf_message_from_bytes(uint8_t *in, BFPublicParameters *params,
                           BFMessage *msg) {
  memcpy(&(msg->length), in, sizeof(size_t));
  in += sizeof(size_t);

  uint8_t level = *in;
  if (level != params->security.level) {
    printf("Wrong security level in decoded message. Expected: %" PRIu8
           ", got: %" PRIu8 "\n",
           params->security.level, level);
    return false;
  }
  in++;

  element_init_G1(msg->U, params->pairing);
  int ele_bytes = element_from_bytes(msg->U, in);
  in += ele_bytes;

  msg->V = malloc(params->security.hashlen);
  memcpy(msg->V, in, params->security.hashlen);
  in += params->security.hashlen;

  msg->W = malloc(msg->length);
  memcpy(msg->W, in, msg->length);

  return true;
}
