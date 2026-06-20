/**
 * @file    camera.h
 * @brief   OV7692 Camera Driver Interface for MAX78000FTHR.
 * @project Edge AI Palm Oil FFB (TBS) Grading System
 *
 * @details Provides a clean driver abstraction over the Maxim MSDK camera
 *          HAL for the OV7692 CMOS image sensor built into the MAX78000FTHR
 *          evaluation board. Configures the sensor for 128x128 pixel output
 *          using hardware windowing/cropping and DMA-based frame transfer to
 *          eliminate CPU stall time during capture.
 *
 * @hardware
 *   - Sensor: OmniVision OV7692 (VGA 640x480 native resolution)
 *   - Interface: DVP (Digital Video Port) 8-bit parallel
 *   - Clock: PCLK supplied by MAX78000 via camera interface
 *   - Connection: On-board ribbon cable on MAX78000FTHR
 *
 * @memory_layout
 *   Frame buffer size: 128 * 128 * 2 bytes (RGB565) = 32,768 bytes (32 KB)
 *   Buffer location: Internal SRAM (statically allocated in camera.c)
 *
 * @usage
 *   1. Call camera_module_init() once at startup.
 *   2. For each frame: call camera_start_dma_capture().
 *   3. Wait for capture via camera_wait_capture_done() or interrupt callback.
 *   4. Access pixel data via camera_get_frame_buffer().
 */

#ifndef PROJECT_CAMERA_DRIVER_H
#define PROJECT_CAMERA_DRIVER_H

#include <stdint.h>
#include <stdbool.h>

/* ── Public Constants ─────────────────────────────────────────────────────── */

/** Target capture width in pixels (CNN input size) */
#define CAMERA_CAPTURE_WIDTH    (128U)

/** Target capture height in pixels (CNN input size) */
#define CAMERA_CAPTURE_HEIGHT   (128U)

/**
 * @brief Bytes per pixel in RGB565 format.
 * Each pixel: 5 bits Red + 6 bits Green + 5 bits Blue = 16 bits = 2 bytes.
 */
#define CAMERA_BYTES_PER_PIXEL  (2U)

/**
 * @brief Total frame buffer size in bytes.
 * 128 * 128 * 2 = 32,768 bytes (32 KB).
 */
#define CAMERA_FRAME_BUFFER_SIZE \
    (CAMERA_CAPTURE_WIDTH * CAMERA_CAPTURE_HEIGHT * CAMERA_BYTES_PER_PIXEL)

/* ── Error Codes ──────────────────────────────────────────────────────────── */

/** Function return codes for camera driver operations. */
typedef enum {
    CAMERA_OK           =  0,  /**< Operation completed successfully */
    CAMERA_ERR_INIT     = -1,  /**< Camera hardware initialization failed */
    CAMERA_ERR_TIMEOUT  = -2,  /**< DMA capture timed out */
    CAMERA_ERR_DMA      = -3,  /**< DMA transfer error */
    CAMERA_ERR_PARAMS   = -4,  /**< Invalid parameter provided */
} camera_status_t;

/* ── Public API ───────────────────────────────────────────────────────────── */

/**
 * @brief  Initialize the OV7692 camera sensor and DMA infrastructure.
 *
 * @details Performs the following sequence:
 *   1. Initializes the MAX78000 camera interface peripheral (DVP port).
 *   2. Sends I2C initialization sequence to OV7692 (reset + register config).
 *   3. Configures hardware windowing registers to output 128x128 pixels
 *      cropped from the center of the native 640x480 frame.
 *   4. Sets pixel format to RGB565 (2 bytes/pixel).
 *   5. Configures DMA channel for non-blocking frame transfer.
 *
 * @note   Must be called ONCE during system startup before any capture.
 * @note   Camera requires ~50ms warm-up time after init before first capture.
 *
 * @return CAMERA_OK on success, negative camera_status_t error code on failure.
 */
camera_status_t camera_module_init(void);

/**
 * @brief  Trigger a non-blocking DMA-based frame capture.
 *
 * @details Starts the OV7692 sensor and configures DMA to transfer one
 *          complete 128x128 frame into the internal frame buffer.
 *          Returns immediately — CPU is free to do other work while DMA runs.
 *          Use camera_wait_capture_done() to block until transfer completes,
 *          or use the interrupt callback via camera_register_done_callback().
 *
 * @note   Do not call this function again until the previous capture has
 *         completed (check camera_is_capture_done() first).
 *
 * @return CAMERA_OK if DMA started successfully, error code otherwise.
 */
camera_status_t camera_start_dma_capture(void);

/**
 * @brief  Block the calling thread until the DMA frame capture completes.
 *
 * @details Polls the DMA completion flag in a tight loop with a timeout guard.
 *          For power efficiency, consider using the interrupt-driven approach
 *          via camera_register_done_callback() and __WFI() instead.
 *
 * @param  timeout_ms Maximum milliseconds to wait before returning timeout.
 *                    Pass 0 for infinite wait (no timeout).
 *
 * @return CAMERA_OK if capture completed within timeout.
 *         CAMERA_ERR_TIMEOUT if timeout elapsed before completion.
 */
camera_status_t camera_wait_capture_done(uint32_t timeout_ms);

/**
 * @brief  Check if the DMA capture has completed without blocking.
 *
 * @return true  if the last capture has finished and buffer is ready.
 *         false if a capture is still in progress.
 */
bool camera_is_capture_done(void);

/**
 * @brief  Get a pointer to the raw frame buffer.
 *
 * @details Returns a pointer to the internal static frame buffer containing
 *          the most recently captured 128x128 RGB565 image.
 *          The buffer is valid until the next call to camera_start_dma_capture().
 *
 * @return Pointer to raw uint8_t frame buffer of size CAMERA_FRAME_BUFFER_SIZE.
 *         Returns NULL if camera is not initialized.
 */
const uint8_t *camera_get_frame_buffer(void);

/**
 * @brief  Register a callback function to be called on DMA capture completion.
 *
 * @details The callback is invoked from the DMA interrupt context (ISR).
 *          Keep callback implementations minimal — set a flag and return.
 *          Avoid UART prints, memory allocation, or complex logic in the ISR.
 *
 * @param  callback Function pointer: void callback(void).
 *                  Pass NULL to disable the callback.
 */
typedef void (*camera_done_callback_t)(void);
void camera_register_done_callback(camera_done_callback_t callback);

/**
 * @brief  Put the camera sensor into hardware standby (power-save) mode.
 *
 * @details Sends the OV7692 standby register command over I2C. Camera draws
 *          minimal current (~0.5 mA) in standby vs ~20 mA active.
 *          Call camera_module_init() or a wake function to resume capture.
 *
 * @return CAMERA_OK on success.
 */
camera_status_t camera_enter_standby(void);

/**
 * @brief  Wake the camera sensor from standby mode.
 *
 * @note   After wake, allow ~30ms before starting a capture for AEC/AGC
 *         (auto-exposure/auto-gain) to stabilize.
 *
 * @return CAMERA_OK on success.
 */
camera_status_t camera_exit_standby(void);

#endif /* PROJECT_CAMERA_DRIVER_H */
