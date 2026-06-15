/**
 * @file    preprocess.c
 * @brief   Image Preprocessing Pipeline Implementation for TBS CNN Input.
 * @project Edge AI Palm Oil FFB (TBS) Grading System
 *
 * @details Converts raw RGB565 camera frames to the INT8 signed HWC tensor
 *          format required by the MAX78000 CNN hardware accelerator input.
 *          Also provides local contrast enhancement to compensate for
 *          LED ring light intensity variations on the conveyor belt.
 */

#include "../include/preprocess.h"
#include "../include/camera.h"

/* MSDK includes */
#include "mxc_device.h"
#include "mxc_sys.h"

#include <stddef.h>
#include <string.h>
#include <stdio.h>

/* ── Private Helper Macros ────────────────────────────────────────────────── */

/**
 * @brief  Clamp an integer value to INT8 range [-128, 127].
 * @param  x  Integer value to clamp.
 */
#define CLAMP_INT8(x)  \
    (((x) < -128) ? ((int8_t)-128) : (((x) > 127) ? ((int8_t)127) : ((int8_t)(x))))

/* ── Public API Implementation ────────────────────────────────────────────── */

preprocess_status_t preprocess_normalize_to_int8(
    const uint8_t *raw_rgb565,
    int8_t        *cnn_input)
{
    /* ── Input validation ─────────────────────────────────────────────────── */
    if (raw_rgb565 == NULL) {
        printf("[PREPROCESS] ERROR: raw_rgb565 is NULL.\r\n");
        return PREPROCESS_ERR_NULL_PTR;
    }
    if (cnn_input == NULL) {
        printf("[PREPROCESS] ERROR: cnn_input is NULL.\r\n");
        return PREPROCESS_ERR_NULL_PTR;
    }

    /* ── Conversion Loop ──────────────────────────────────────────────────── */
    /*
     * The raw_rgb565 buffer is laid out as:
     *   [MSB_pixel0, LSB_pixel0, MSB_pixel1, LSB_pixel1, ...]
     *   where each pixel is a 16-bit RGB565 value stored big-endian.
     *
     * RGB565 bit layout:
     *   Byte 0 (MSB): [R4 R3 R2 R1 R0 | G5 G4 G3]
     *   Byte 1 (LSB): [G2 G1 G0 | B4 B3 B2 B1 B0]
     *
     * Channel extraction to 8-bit:
     *   R8 = (MSB >> 3) & 0x1F, then scale to 8-bit: R8 = (R5 << 3) | (R5 >> 2)
     *   G8 = ((MSB & 0x07) << 3) | ((LSB >> 5) & 0x07), scale: G6 << 2 | G6 >> 4
     *   B8 = (LSB & 0x1F), scale: B5 << 3 | B5 >> 2
     *
     * Then normalize: int8_val = (int8_t)(uint8_val - 128)
     *
     * HWC output layout: [R0, G0, B0, R1, G1, B1, ..., R_N-1, G_N-1, B_N-1]
     * Total: 128 * 128 * 3 = 49,152 bytes
     */

    const uint32_t num_pixels = PREPROCESS_IMG_WIDTH * PREPROCESS_IMG_HEIGHT;
    uint32_t out_idx = 0;  /* Index into cnn_input[] */

    for (uint32_t px = 0; px < num_pixels; px++) {
        /* Load two bytes for this pixel (big-endian RGB565) */
        uint8_t msb = raw_rgb565[px * 2];        /* Byte with R and G upper bits */
        uint8_t lsb = raw_rgb565[px * 2 + 1];    /* Byte with G lower bits and B */

        /* ── Extract 5-bit Red channel ───────────────────────────────────── */
        uint8_t r5 = (msb >> 3) & 0x1F;
        /* Scale 5-bit [0..31] to 8-bit [0..255]: multiply by 8.226...
         * Efficient approximation: r8 = (r5 << 3) | (r5 >> 2)
         * This fills the lower bits with the upper bits — standard technique. */
        uint8_t r8 = (uint8_t)((r5 << 3) | (r5 >> 2));

        /* ── Extract 6-bit Green channel ─────────────────────────────────── */
        uint8_t g6 = (uint8_t)(((msb & 0x07) << 3) | ((lsb >> 5) & 0x07));
        /* Scale 6-bit [0..63] to 8-bit [0..255]: g8 = (g6 << 2) | (g6 >> 4) */
        uint8_t g8 = (uint8_t)((g6 << 2) | (g6 >> 4));

        /* ── Extract 5-bit Blue channel ──────────────────────────────────── */
        uint8_t b5 = lsb & 0x1F;
        /* Scale 5-bit to 8-bit (same as R) */
        uint8_t b8 = (uint8_t)((b5 << 3) | (b5 >> 2));

        /* ── Normalize to INT8 signed: pixel_int8 = (uint8_val - 128) ───── */
        /* This maps:
         *   0    → -128  (pure black)
         *   128  →    0  (mid-gray)
         *   255  →  127  (pure white / saturated) */
        cnn_input[out_idx++] = (int8_t)((int16_t)r8 - 128);
        cnn_input[out_idx++] = (int8_t)((int16_t)g8 - 128);
        cnn_input[out_idx++] = (int8_t)((int16_t)b8 - 128);
    }

    return PREPROCESS_OK;
}

preprocess_status_t preprocess_contrast_enhance(int8_t *cnn_input)
{
    if (cnn_input == NULL) {
        printf("[PREPROCESS] ERROR: cnn_input is NULL in contrast_enhance.\r\n");
        return PREPROCESS_ERR_NULL_PTR;
    }

    /*
     * Fast Global Channel Mean Subtraction (Contrast Normalization)
     * ──────────────────────────────────────────────────────────────
     * Problem: The industrial LED ring light may have uneven illumination
     *          across the conveyor scan zone (center brighter than edges).
     *          This creates a global DC offset in the image that can
     *          shift the INT8 activations toward one side of the range.
     *
     * Solution: Subtract the per-channel mean from every pixel of that channel.
     *           This centers each channel around zero, maximizing the dynamic
     *           range of INT8 [-128, 127] and improving CNN feature discrimination.
     *
     * Algorithm (per channel c in {R, G, B}):
     *   1. Compute mean_c = sum(channel_c pixels) / num_pixels
     *   2. Subtract: pixel[c] -= mean_c  (clamped to INT8 range)
     *
     * Complexity: O(N) with N = 128*128*3 = 49,152 iterations.
     *             Executes in ~0.5 ms at 100 MHz on Cortex-M4F.
     */

    const uint32_t num_pixels = PREPROCESS_IMG_WIDTH * PREPROCESS_IMG_HEIGHT;

    /* Compute per-channel mean using int32 accumulator to avoid overflow.
     * Max sum: 127 * 128 * 128 = 2,080,768 — well within int32_t range. */
    int32_t mean_r = 0, mean_g = 0, mean_b = 0;

    for (uint32_t px = 0; px < num_pixels; px++) {
        mean_r += (int32_t)cnn_input[px * 3 + 0];
        mean_g += (int32_t)cnn_input[px * 3 + 1];
        mean_b += (int32_t)cnn_input[px * 3 + 2];
    }

    /* Divide to get integer mean (truncated — acceptable for DC subtraction) */
    mean_r /= (int32_t)num_pixels;
    mean_g /= (int32_t)num_pixels;
    mean_b /= (int32_t)num_pixels;

    /* Subtract mean from each channel and clamp result to INT8 range */
    for (uint32_t px = 0; px < num_pixels; px++) {
        int32_t r = (int32_t)cnn_input[px * 3 + 0] - mean_r;
        int32_t g = (int32_t)cnn_input[px * 3 + 1] - mean_g;
        int32_t b = (int32_t)cnn_input[px * 3 + 2] - mean_b;

        cnn_input[px * 3 + 0] = CLAMP_INT8(r);
        cnn_input[px * 3 + 1] = CLAMP_INT8(g);
        cnn_input[px * 3 + 2] = CLAMP_INT8(b);
    }

    return PREPROCESS_OK;
}

preprocess_status_t preprocess_load_into_cnn_sram(const int8_t *cnn_input)
{
    if (cnn_input == NULL) {
        printf("[PREPROCESS] ERROR: cnn_input is NULL in load_into_cnn_sram.\r\n");
        return PREPROCESS_ERR_NULL_PTR;
    }

    /*
     * CNN Input SRAM Base Address
     * ───────────────────────────
     * The MAX78000 CNN accelerator has dedicated data SRAM organized into
     * 64 processors × 4 memory instances. The base address is defined in
     * the MSDK as MXC_CNN_DATA_SRAM_BASE (typically 0x50400000).
     *
     * The ai8x-synthesis generated cnn_load_input() function writes to this
     * region in a specific mexpress-optimized format. For custom DMA loading,
     * the HWC tensor is written as 32-bit words to consecutive SRAM addresses.
     *
     * NOTE: In most production implementations, you will call the generated
     *       cnn_load_input() function from tbs_cnn.c directly, passing the
     *       cnn_input buffer as an argument (or setting a global pointer).
     *       This function serves as a documented reference for the memory
     *       layout, and for cases where a custom loader is needed.
     *
     * For simplicity, we call the generated API here:
     */
    extern void cnn_load_input(void);   /* Declared in cnn_generated/tbs_cnn.h */

    /*
     * The generated cnn_load_input() reads from a global input buffer.
     * We expose the buffer via a global pointer that the generated code reads.
     * This pattern is used in all MSDK CNN examples.
     *
     * Set the external input pointer that tbs_cnn.c will read from:
     */
    extern const int8_t *g_cnn_input_ptr;  /* Defined in cnn_inference.c */
    g_cnn_input_ptr = cnn_input;

    /* Trigger the generated loader */
    cnn_load_input();

    return PREPROCESS_OK;
}
