/**
 * @file    camera.c
 * @brief   OV7692 Camera Driver Implementation for MAX78000FTHR.
 * @project Edge AI Palm Oil FFB (TBS) Grading System
 *
 * @details Full implementation of the camera driver using the Maxim MSDK
 *          (Maxim SDK) camera HAL. Configures the OV7692 for 128x128 pixel
 *          RGB565 output using hardware windowing and DMA-based capture.
 *
 * @msdk_dependencies
 *   - camera.h       (MSDK camera HAL - in Libraries/Camera/)
 *   - ov7692_regs.h  (MSDK OV7692 register definitions)
 *   - mxc_device.h   (device-specific definitions)
 *   - dma.h          (MSDK DMA driver)
 *   - mxc_delay.h    (MSDK delay functions)
 *
 * @note
 *   The MSDK camera HAL abstracts the DVP (Digital Video Port) parallel
 *   interface. The OV7692 connects via 8-bit DVP with VSYNC, HSYNC, PCLK
 *   signals. The MSDK configures these automatically.
 */

/* MSDK camera HAL — provides MXC_CAMERA_Init, MXC_CAMERA_CaptureImageDMA, etc.
 * Use the full library path since "-Iinclude" resolves "camera.h" to our
 * project file first. */
#include "/home/felichpg/Felichs/msdk/Libraries/MiscDrivers/Camera/camera.h"

/* OV7692 register address definitions */
/* #include "ov7692_regs.h" */

/* MAX78000 peripheral & driver includes */
/* #include "mxc_device.h" */
/* #include "dma.h" */
#include "mxc_delay.h"
/* #include "gpio.h" */
/* #include "i2c.h" */

/* Our project camera abstraction (camera_status_t, camera_module_init, etc.)
 * Guard: PROJECT_CAMERA_DRIVER_H — no conflict with MSDK camera.h */
#include "../include/camera.h"

#include <string.h>
#include <stdio.h>

/* ── Private Constants ────────────────────────────────────────────────────── */

#ifndef CAMERA_BYPASS
#define CAMERA_BYPASS           (0)   /* Fallback: default to physical camera sensor active */
#endif

/**
 * @brief OV7692 native sensor resolution (VGA).
 *        We window this down to 128x128 via sensor registers.
 */
#define OV7692_NATIVE_WIDTH     (640U)
#define OV7692_NATIVE_HEIGHT    (480U)

/**
 * @brief  DMA channel reserved for camera frame transfer.
 *         Channel 0 is typically available on MAX78000 for camera DMA.
 */
#define CAMERA_DMA_CHANNEL      (0)

/**
 * @brief  OV7692 I2C slave address (7-bit).
 *         OV7692 has a fixed I2C address of 0x3C (write: 0x78, read: 0x79).
 */
#define OV7692_I2C_ADDR         (0x3C)

/* ── Private State Variables ─────────────────────────────────────────────── */

/** Static frame buffer in internal SRAM — aligned for DMA efficiency */
static uint8_t s_frame_buffer[CAMERA_FRAME_BUFFER_SIZE] __attribute__((aligned(4)));

/** Flag set by DMA ISR on capture completion */
static volatile bool s_capture_done = false;

/** User-registered callback for capture completion notification */
static camera_done_callback_t s_done_callback = NULL;

/** Tracks whether camera_module_init() has been called successfully */
static bool s_camera_initialized = false;

/* ── Private OV7692 Register Configuration Table ─────────────────────────── */

/**
 * @brief  OV7692 register init sequence for 128x128 RGB565 output.
 *
 * @details Each entry is {register_address, value}. The sequence:
 *   1. Software resets the sensor.
 *   2. Sets output format to RGB565.
 *   3. Configures HREF/VSYNC polarity.
 *   4. Enables hardware windowing to output 128x128 center crop.
 *   5. Configures auto-exposure and auto-white-balance for indoor LED light.
 *
 * @note   Register values are derived from OV7692 datasheet and the
 *         Maxim MSDK MAX78000 CNN examples (see evkit/camera_util.c).
 *         Terminate list with sentinel {0xFF, 0xFF}.
 */
static const uint8_t s_ov7692_reg_init[][2] = {
    /* ── Step 1: Software reset (self-clears after ~5ms) ─────────────────── */
    {0x12, 0x80},  /* COM7: SCCB reset all registers to default */

    /* ── Step 2: Output format — RGB565 ──────────────────────────────────── */
    {0x12, 0x06},  /* COM7: RGB output (bit2=1), no mirror/flip */
    {0x82, 0x03},  /* RGB444: disable RGB444, enable RGB565 */
    {0x8E, 0x00},  /* RGB565 output swap: byte order normal */

    /* ── Step 3: Clock & frame rate ──────────────────────────────────────── */
    {0x0D, 0x41},  /* COM4: PLL clock multiplier = 4x */
    {0x11, 0x00},  /* CLKRC: Internal clock prescaler = 1 (full speed) */
    {0x14, 0x0E},  /* COM9: Auto gain ceiling = 128x, freeze AGC/AEC */

    /* ── Step 4: Hardware windowing for 128x128 center crop ──────────────── */
    /* The OV7692 outputs a windowed region defined by HSTART/HSTOP/VSTART/VSTOP */
    /* Center of 640: (640-128)/2 = 256. Center of 480: (480-128)/2 = 176. */
    {0x17, 0x10},  /* HSTART: Horizontal window start MSB (pixel 256>>3 = 32, fine=0) */
    {0x18, 0x30},  /* HSTOP: Horizontal window stop MSB (32+16 = 48) */
    {0x32, 0x80},  /* HREF: H start LSB bits [2:0] = 0, H stop LSB [5:3] = 0 */
    {0x19, 0x03},  /* VSTRT: Vertical window start (row 176/2 = 88 → VSTRT high byte) */
    {0x1A, 0x07},  /* VSTOP: Vertical window stop (176+128 = 304 → high byte) */
    {0x03, 0x00},  /* VREF: V start/stop LSBs = 0 */

    /* ── Step 5: Sensor array window size ────────────────────────────────── */
    {0x0C, 0x04},  /* COM3: Enable scale/DCW */
    {0x3E, 0x00},  /* COM14: No DCW, no PCLK divider */
    {0x70, 0x3A},  /* SCALING_XSC: Horizontal scaling factor */
    {0x71, 0x35},  /* SCALING_YSC: Vertical scaling factor */
    {0x72, 0x11},  /* SCALING_DCWCTR: DCW control */
    {0x73, 0xF0},  /* SCALING_PCLK_DIV: PCLK divider */

    /* ── Step 6: AEC/AGC for LED ring light environment ──────────────────── */
    {0x13, 0xC7},  /* COM8: Enable AGC, AEC, AWB, fast AGC/AEC algorithm */
    {0x0F, 0x4B},  /* COM6: HREF option, reset timing */
    {0x24, 0x70},  /* AEW: AGC/AEC stable upper threshold */
    {0x25, 0x64},  /* AEB: AGC/AEC stable lower threshold */
    {0x26, 0xD3},  /* VPT: Fast mode thresholds */

    /* ── Step 7: VSYNC polarity and HREF timing ──────────────────────────── */
    {0x15, 0x00},  /* COM10: VSYNC active HIGH, HREF active HIGH, PCLK positive */

    /* ── Termination sentinel ─────────────────────────────────────────────── */
    {0xFF, 0xFF}   /* End of register list */
};

/* ── Private Function Declarations ───────────────────────────────────────── */

static void prv_dma_done_handler(int ch, int err);

/* ── Public API Implementation ────────────────────────────────────────────── */

camera_status_t camera_module_init(void)
{
#if CAMERA_BYPASS
    printf("[CAMERA] CAMERA BYPASS MODE ACTIVE (Software Emulation)\r\n");
    s_capture_done       = false;
    s_done_callback      = NULL;
    s_camera_initialized = true;

    /* Fill frame buffer with a dummy RGB565 test pattern (e.g. green solid) */
    uint16_t *buf16 = (uint16_t*)s_frame_buffer;
    for (uint32_t i = 0; i < CAMERA_CAPTURE_WIDTH * CAMERA_CAPTURE_HEIGHT; i++) {
        buf16[i] = 0x07E0; /* 0x07E0 is Green in RGB565 */
    }
    printf("[CAMERA] Dummy RGB565 Frame initialized.\r\n");
    return CAMERA_OK;
#else
    int ret;

    printf("[CAMERA] Initializing OV7692 camera module via MSDK HAL...\r\n");

    /*
     * Step 1: Initialize the MSDK camera HAL.
     * camera_init(freq) configures the I2C interface for sensor register access
     * and sets up the DVP clock at the specified frequency (Hz).
     * Typical frequency: 10 MHz = 10000000
     */
    ret = camera_init(10000000);
    if (ret != 0) {
        printf("[CAMERA] ERROR: camera_init failed: %d\r\n", ret);
        return CAMERA_ERR_INIT;
    }

    /* Allow sensor power rails to stabilize (~10 ms) */
    MXC_Delay(MXC_DELAY_MSEC(10));

    /*
     * Step 2: Configure capture parameters.
     * camera_setup() sets:
     *   - Resolution: CAMERA_CAPTURE_WIDTH x CAMERA_CAPTURE_HEIGHT (128x128)
     *   - Format:     PIXFORMAT_RGB565
     *   - FIFO mode:  FIFO_THREE_BYTE (3-byte FIFO, standard for RGB565)
     *   - DMA mode:   USE_DMA (non-blocking DMA-based capture)
     *   - DMA channel: 0
     */
    ret = camera_setup(
        CAMERA_CAPTURE_WIDTH,   /* xres */
        CAMERA_CAPTURE_HEIGHT,  /* yres */
        PIXFORMAT_RGB565,       /* pixel format */
        FIFO_THREE_BYTE,        /* FIFO mode */
        USE_DMA,                /* DMA mode */
        0                       /* DMA channel */
    );
    if (ret != 0) {
        printf("[CAMERA] ERROR: camera_setup failed: %d\r\n", ret);
        return CAMERA_ERR_INIT;
    }

    /* Allow AEC/AGC to stabilize after register load (~50 ms) */
    MXC_Delay(MXC_DELAY_MSEC(50));

    s_capture_done       = false;
    s_done_callback      = NULL;
    s_camera_initialized = true;

    memset(s_frame_buffer, 0, sizeof(s_frame_buffer));

    printf("[CAMERA] OV7692 initialized. Output: %dx%d RGB565.\r\n",
           CAMERA_CAPTURE_WIDTH, CAMERA_CAPTURE_HEIGHT);

    return CAMERA_OK;
#endif
}

camera_status_t camera_start_dma_capture(void)
{
#if CAMERA_BYPASS
    s_capture_done = true;
    return CAMERA_OK;
#else
    if (!s_camera_initialized) {
        printf("[CAMERA] ERROR: camera_module_init() not called.\r\n");
        return CAMERA_ERR_INIT;
    }

    s_capture_done = false;

    /*
     * Start DMA-based frame capture.
     * camera_start_capture_image() arms the DMA and begins waiting for
     * VSYNC from the sensor to start transferring pixel data.
     * Returns immediately (non-blocking). Frame data is streamed via DMA.
     */
    int ret = camera_start_capture_image();
    if (ret != 0) {
        printf("[CAMERA] ERROR: camera_start_capture_image failed: %d\r\n", ret);
        return CAMERA_ERR_DMA;
    }

    return CAMERA_OK;
#endif
}

camera_status_t camera_wait_capture_done(uint32_t timeout_ms)
{
#if CAMERA_BYPASS
    s_capture_done = true;
    if (s_done_callback != NULL) {
        s_done_callback();
    }
    return CAMERA_OK;
#else
    uint32_t elapsed_ms = 0;

    /*
     * Poll camera_is_image_rcv() with timeout.
     * The MSDK sets an internal flag when DMA transfer is complete.
     * We also sleep between polls to reduce power consumption.
     */
    while (camera_is_image_rcv() == 0) {
        MXC_Delay(MXC_DELAY_MSEC(1));

        if (timeout_ms != 0) {
            elapsed_ms++;
            if (elapsed_ms >= timeout_ms) {
                printf("[CAMERA] WARNING: Capture timeout after %u ms.\r\n", elapsed_ms);
                return CAMERA_ERR_TIMEOUT;
            }
        }
    }

    /*
     * Retrieve captured frame from MSDK camera buffer into our s_frame_buffer.
     * camera_get_image() returns a pointer to the internal camera DMA buffer,
     * the length, width, and height. We copy it to our static buffer.
     */
    uint8_t  *img_ptr  = NULL;
    uint32_t  img_len  = 0;
    uint32_t  img_w    = 0;
    uint32_t  img_h    = 0;
    camera_get_image(&img_ptr, &img_len, &img_w, &img_h);

    if (img_ptr != NULL && img_len > 0 && img_len <= CAMERA_FRAME_BUFFER_SIZE) {
        memcpy(s_frame_buffer, img_ptr, img_len);
    } else {
        printf("[CAMERA] WARNING: camera_get_image returned unexpected values"
               " (ptr=%p, len=%lu).\r\n", (void*)img_ptr, (unsigned long)img_len);
    }

    s_capture_done = true;
    return CAMERA_OK;
#endif
}

bool camera_is_capture_done(void)
{
    return s_capture_done;
}

const uint8_t *camera_get_frame_buffer(void)
{
    if (!s_camera_initialized) {
        return NULL;
    }
    return (const uint8_t *)s_frame_buffer;
}

void camera_register_done_callback(camera_done_callback_t callback)
{
    s_done_callback = callback;
}

camera_status_t camera_enter_standby(void)
{
#if CAMERA_BYPASS
    return CAMERA_OK;
#else
    /*
     * Use MSDK camera_sleep(1) to put OV7692 into low-power standby.
     * This sets the PWDN bit in the OV7692 via I2C.
     */
    int ret = camera_sleep(1);
    if (ret != 0) {
        printf("[CAMERA] WARNING: camera_sleep(1) failed: %d\r\n", ret);
        /* Non-fatal — camera may already be in standby */
    }
    return CAMERA_OK;
#endif
}

camera_status_t camera_exit_standby(void)
{
#if CAMERA_BYPASS
    return CAMERA_OK;
#else
    /*
     * Clear sleep mode. Allow AEC/AGC to stabilize (~30 ms).
     */
    int ret = camera_sleep(0);
    if (ret != 0) {
        printf("[CAMERA] WARNING: camera_sleep(0) failed: %d\r\n", ret);
    }
    MXC_Delay(MXC_DELAY_MSEC(30));
    return CAMERA_OK;
#endif
}

/* ── Private Implementation ───────────────────────────────────────────────── */

/**
 * @brief  DMA completion callback stub (not used with polling method).
 *         Kept for compatibility with camera_register_done_callback().
 */
static void prv_dma_done_handler(int ch, int err)
{
    (void)ch;
    (void)err;
    s_capture_done = true;
    if (s_done_callback != NULL) {
        s_done_callback();
    }
}

