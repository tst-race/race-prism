/*
 * Copyright (c) 2019-2020 SRI International.
 * All rights reserved.
 */

#include <jni.h>
#include <bfibe.h>

#ifdef ANDROID
#include <android/log.h>
static const char *LOG_TAG="BFIBE";
#endif

#ifdef ANDROID
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, LOG_TAG, __VA_ARGS__)
#else
#define LOGD(...) printf(__VA_ARGS__)
#endif

void print_bytes(const char* label, uint8_t *bytes, size_t length) {
    char *buf = calloc(length * 2 + 1, sizeof(char));

    for(size_t i = 0; i < length; i++) {
        sprintf(buf+(i*2), "%02X", bytes[i]);
    }

    *(buf+(length*2)) = 0;

    free(buf);
}

void print_element(const char* label, element_t e) {
    char buf[4096];
    element_snprintf(buf, 4096, "%s: %B", label, e);
}

BFPublicParameters *getParams(JNIEnv *env, jobject this)
{
    jclass cls = (*env)->GetObjectClass(env, this);
    jfieldID fieldId = (*env)->GetFieldID(env, cls, "systemParamHandle", "J");
    return (BFPublicParameters *) (*env)->GetLongField(env, this, fieldId);
}

element_t *getPrivateKey(JNIEnv *env, jobject this)
{
    jclass cls = (*env)->GetObjectClass(env, this);
    jfieldID fieldId = (*env)->GetFieldID(env, cls, "privateKeyHandle", "J");
    return (element_t *) (*env)->GetLongField(env, this, fieldId);
}

JNIEXPORT jlong
JNICALL Java_com_sri_csl_prism_crypto_BonehFranklin_parseSystemParams(
        JNIEnv *env,
        jobject this,
        jstring paramString)
{
    const char *str = (*env)->GetStringUTFChars(env, paramString, NULL);
    BFPublicParameters *params = getParams(env, this);

    if (params == NULL) {
        params = calloc(1, sizeof(*params));
    }

    bf_params_from_string((uint8_t *)str, params);

    (*env)->ReleaseStringUTFChars(env, paramString, str);
    return (long) params;
}

JNIEXPORT jlong
JNICALL Java_com_sri_csl_prism_crypto_BonehFranklin_parsePrivateKey(
        JNIEnv *env,
        jobject this,
        jstring keyString)
{
    const char *str = (*env)->GetStringUTFChars(env, keyString, NULL);
    BFPublicParameters *params = getParams(env, this);

    element_t *privateKey = getPrivateKey(env, this);

    if (privateKey == NULL) {
        privateKey = calloc(1, sizeof(*privateKey));
    } else {
        element_clear(*privateKey);
    }

    element_init_G2(*privateKey, params->pairing);
    element_set_str(*privateKey, str, 10);

    (*env)->ReleaseStringUTFChars(env, keyString, str);
    return (long) privateKey;
}

JNIEXPORT jbyteArray
JNICALL Java_com_sri_csl_prism_crypto_BonehFranklin_encryptIBE(
        JNIEnv *env,
        jobject this,
        jstring recipient,
        jbyteArray message)
{
    BFPublicParameters *params = getParams(env, this);
    element_t publicKey;
    element_init_G2(publicKey, params->pairing);
    const char *recipientStr = (*env)->GetStringUTFChars(env, recipient, NULL);
    bf_generate_public_key(publicKey, params, (char *)recipientStr);

    jbyte *messageBytes = (*env)->GetByteArrayElements(env, message, NULL);
    jsize messageLength = (*env)->GetArrayLength(env, message);

    BFMessage *cipherText = bf_encrypt(params, publicKey, (uint8_t *)messageBytes, messageLength);

    uint8_t *cipherBytes;
    size_t cipherLength = bf_message_to_bytes(&cipherBytes, params, cipherText);

    jbyteArray retval = (*env)->NewByteArray(env, cipherLength);
    (*env)->SetByteArrayRegion(env, retval, 0, cipherLength, (jbyte*)cipherBytes);

    free(cipherText->V);
    free(cipherText->W);
    free(cipherText);
    free(cipherBytes);
    element_clear(publicKey);
    (*env)->ReleaseByteArrayElements(env, message, messageBytes, JNI_ABORT);

    return retval;
}

JNIEXPORT jbyteArray
JNICALL Java_com_sri_csl_prism_crypto_BonehFranklin_decryptIBE(
        JNIEnv *env,
        jobject this,
        jbyteArray cipherText)
{
    BFPublicParameters *params = getParams(env, this);
    element_t *privateKey = getPrivateKey(env, this);
    jbyte *cipherBytes = (*env)->GetByteArrayElements(env, cipherText, NULL);

    BFMessage msg;
    if (!bf_message_from_bytes((uint8_t *)cipherBytes, params, &msg)) {
        (*env)->ReleaseByteArrayElements(env, cipherText, cipherBytes, JNI_ABORT);
        return NULL;
    }

    uint8_t msgBytes[msg.length];
    bf_decrypt(msgBytes, params, *privateKey, &msg);

    jbyteArray retval = (*env)->NewByteArray(env, msg.length);
    (*env)->SetByteArrayRegion(env, retval, 0, msg.length, (jbyte*)msgBytes);

    free(msg.V);
    free(msg.W);
    (*env)->ReleaseByteArrayElements(env, cipherText, cipherBytes, JNI_ABORT);

    return retval;
}

