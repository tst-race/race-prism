#pragma once
#include <stdint.h>
#include <stdio.h>

uint8_t *base64_decode(uint8_t *b64message, size_t *decode_len);
uint8_t *base64_encode(uint8_t *buffer, size_t length);
