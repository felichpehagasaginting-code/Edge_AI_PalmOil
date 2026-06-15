/**
 * @file    tbs_cnn.h
 * @brief   STUB: ai8x-synthesis Generated CNN API for TBS Grading.
 * @project Edge AI Palm Oil FFB (TBS) Grading System
 *
 * ╔══════════════════════════════════════════════════════════════════════╗
 * ║  IMPORTANT: THIS FILE IS A PLACEHOLDER/STUB                        ║
 * ║                                                                      ║
 * ║  This file defines the expected API contract that will be fulfilled  ║
 * ║  by the actual generated tbs_cnn.h produced by the ai8x-synthesis   ║
 * ║  SDK tool (ai8xize.py).                                             ║
 * ║                                                                      ║
 * ║  Replace this stub with the real generated file after running:      ║
 * ║    python ai8xize.py --prefix tbs_cnn ...                           ║
 * ║  (See: 1_ai_training/README_synthesis.md for full instructions)     ║
 * ╚══════════════════════════════════════════════════════════════════════╝
 *
 * @note   The actual generated file will have the same function signatures
 *         but may include additional internal helper declarations.
 *         Do NOT modify function signatures below — they must match exactly.
 */

#ifndef TBS_CNN_H
#define TBS_CNN_H

#include <stdint.h>

/* ── CNN API Contract (fulfilled by ai8x-synthesis generated code) ────────── */

/**
 * @brief  Enable CNN peripheral clock and power up CNN SRAM banks.
 * @param  clock_source  CNN clock source (e.g., MXC_S_GCR_PCLKDIV_CNNCLKSEL_PCLK)
 * @param  clock_div     CNN clock divider (e.g., MXC_S_GCR_PCLKDIV_CNNCLKDIV_DIV1)
 * @return 0 (CNN_OK) on success, non-zero on failure.
 */
int cnn_enable(uint32_t clock_source, uint32_t clock_div);

/**
 * @brief  Load compiled weight arrays from flash into CNN weight SRAM.
 *         Weight data is sourced from weights.h (included in tbs_cnn.c).
 * @return 0 (CNN_OK) on success.
 */
int cnn_load_weights(void);

/**
 * @brief  Load bias values into CNN bias SRAM.
 *         Typically a no-op for bias-free models.
 * @return 0 (CNN_OK) on success.
 */
int cnn_load_bias(void);

/**
 * @brief  Configure CNN layer topology registers.
 *         Programs all layer configuration memory based on synthesis output.
 * @return 0 (CNN_OK) on success.
 */
int cnn_configure(void);

/**
 * @brief  Write input image tensor into CNN input data SRAM.
 *         Reads pixel data from the global g_cnn_input_ptr pointer.
 *         Called by preprocess.c after setting g_cnn_input_ptr.
 */
void cnn_input_load(void);

/**
 * @brief  Start CNN hardware accelerator execution.
 *         Returns immediately — inference runs asynchronously.
 *         Poll MXC_CNN_CheckComplete() or wait for CNN IRQ.
 */
void cnn_start(void);

/**
 * @brief  Read output logits from CNN output SRAM into caller's buffer.
 * @param  out_buf  Pointer to array of CNN_NUM_CLASSES uint32_t values.
 *                  Values are INT32 logits cast to uint32_t by the generated code.
 */
void cnn_unload(uint32_t *out_buf);

/**
 * @brief  Disable CNN peripheral (clock gate + SRAM power down).
 *         Weights are lost — call cnn_load_weights() before next inference.
 * @return 0 (CNN_OK) on success.
 */
int cnn_disable(void);

/* ── MSDK Helper (from mxc_cnn.h) ─────────────────────────────────────────── */

/**
 * @brief  Check whether the CNN accelerator has finished inference.
 * @return Non-zero (true) if CNN is done, 0 (false) if still running.
 *         Implemented in MSDK Libraries/PeriphDrivers/Source/CNN/cnn_me17.c
 */
int MXC_CNN_CheckComplete(void);

#endif /* TBS_CNN_H */
