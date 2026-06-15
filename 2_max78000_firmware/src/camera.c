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

#include "camera.h"

/* MSDK HAL includes — path relative to MSDK Libraries/ directory */
#include "camera.h"          /* MSDK camera HAL (not our project camera.h — resolved by include order) */
#include "ov7692_regs.h"     /* OV7692 register address definitions */
#include "mxc_device.h"      /* MAX78000 peripheral base addresses */
#include "dma.h"             /* DMA driver */
#include "mxc_delay.h"       /* Microsecond/millisecond delay */
#include "gpio.h"            /* GPIO driver for camera power/reset pins */

/* Our project's camera header */
#undef CAMERA_H              /* Temporarily undefine to prevent conflict */
#include "../include/camera.h"

#include <string.h>
#include <stdio.h>

/* ── Private Constants ────────────────────────────────────────────────────── */

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

static int  prv_ov7692_write_reg(uint8_t reg_addr, uint8_t value);
static int  prv_ov7692_write_reg_sequence(const uint8_t regs[][2]);
static void prv_dma_done_handler(int ch, int err);

/* ── Public API Implementation ────────────────────────────────────────────── */

camera_status_t camera_module_init(void)
{
    int ret;

    printf("[CAMERA] Initializing OV7692 camera module...\r\n");

    /* Step 1: Initialize the MSDK camera interface peripheral.
     * MXC_CAMERA_Init() configures the DVP parallel port pins, sets up
     * the camera clock (PCLK), and enables the camera peripheral clock. */
    ret = MXC_CAMERA_Init();
    if (ret != E_NO_ERROR) {
        printf("[CAMERA] ERROR: MXC_CAMERA_Init failed: %d\r\n", ret);
        return CAMERA_ERR_INIT;
    }

    /* Step 2: Allow sensor power rails to stabilize.
     * OV7692 datasheet specifies a minimum 5ms after power-on before I2C. */
    MXC_Delay(MXC_DELAY_MSEC(10));

    /* Step 3: Send the OV7692 software reset (first entry in reg table) and
     * then wait for the reset to complete (~5ms self-clearing). */
    ret = prv_ov7692_write_reg(0x12, 0x80);  /* COM7: software reset */
    if (ret != 0) {
        printf("[CAMERA] ERROR: OV7692 software reset I2C write failed: %d\r\n", ret);
        return CAMERA_ERR_INIT;
    }
    MXC_Delay(MXC_DELAY_MSEC(10));  /* Wait for reset to complete */

    /* Step 4: Write the full register initialization sequence.
     * This configures: RGB565 output, 128x128 hardware window, AEC/AGC. */
    ret = prv_ov7692_write_reg_sequence(s_ov7692_reg_init);
    if (ret != 0) {
        printf("[CAMERA] ERROR: OV7692 register init sequence failed at reg: %d\r\n", ret);
        return CAMERA_ERR_INIT;
    }

    /* Step 5: Configure DMA channel for camera frame buffer transfer.
     * MXC_DMA_Init() prepares the DMA controller. The DMA channel is
     * configured once here; each capture re-arms the same channel. */
    ret = MXC_DMA_Init();
    if (ret != E_NO_ERROR) {
        printf("[CAMERA] ERROR: MXC_DMA_Init failed: %d\r\n", ret);
        return CAMERA_ERR_DMA;
    }

    /* Register DMA completion callback */
    ret = MXC_DMA_AcquireChannel();
    if (ret < 0) {
        printf("[CAMERA] ERROR: Failed to acquire DMA channel: %d\r\n", ret);
        return CAMERA_ERR_DMA;
    }
    /* Note: The MSDK camera HAL manages the DMA internally via MXC_CAMERA_CaptureImage().
     * The channel number above is for reference; the camera HAL uses its own channel. */

    /* Step 6: Allow camera sensor to stabilize AEC/AGC after register load.
     * Recommend 50ms warm-up for stable first frame. */
    MXC_Delay(MXC_DELAY_MSEC(50));

    /* Initialize state */
    s_capture_done    = false;
    s_done_callback   = NULL;
    s_camera_initialized = true;

    /* Clear frame buffer */
    memset(s_frame_buffer, 0, sizeof(s_frame_buffer));

    printf("[CAMERA] OV7692 initialized. Output: %dx%d RGB565.\r\n",
           CAMERA_CAPTURE_WIDTH, CAMERA_CAPTURE_HEIGHT);

    return CAMERA_OK;
}

camera_status_t camera_start_dma_capture(void)
{
    if (!s_camera_initialized) {
        printf("[CAMERA] ERROR: camera_module_init() not called.\r\n");
        return CAMERA_ERR_INIT;
    }

    /* Reset completion flag before starting new capture */
    s_capture_done = false;

    /* Configure the MSDK camera HAL to capture one frame into s_frame_buffer.
     *
     * MXC_CAMERA_CaptureImage() parameters:
     *   - buffer:       Destination frame buffer pointer
     *   - buffer_size:  Expected bytes (width * height * bytes_per_pixel)
     *   - pixel_format: PIXFORMAT_RGB565 (as defined in MSDK camera.h)
     *   - img_width:    Target image width (128)
     *   - img_height:   Target image height (128)
     *
     * The MSDK internally configures DMA and returns immediately after
     * programming the DMA registers (non-blocking). Frame data is
     * transferred automatically as the sensor outputs pixels via DVP.
     */
    int ret = MXC_CAMERA_CaptureImageDMA(
        s_frame_buffer,
        CAMERA_FRAME_BUFFER_SIZE,
        PIXFORMAT_RGB565,
        CAMERA_CAPTURE_WIDTH,
        CAMERA_CAPTURE_HEIGHT,
        prv_dma_done_handler  /* Called from DMA ISR on completion */
    );

    if (ret != E_NO_ERROR) {
        printf("[CAMERA] ERROR: MXC_CAMERA_CaptureImageDMA failed: %d\r\n", ret);
        return CAMERA_ERR_DMA;
    }

    return CAMERA_OK;
}

camera_status_t camera_wait_capture_done(uint32_t timeout_ms)
{
    uint32_t elapsed_ms = 0;
    const uint32_t poll_interval_ms = 1;

    /* Poll the completion flag with timeout guard.
     * For power efficiency, use __WFI() here to sleep between polls.
     * The DMA interrupt will wake the core when capture completes. */
    while (!s_capture_done) {
        __WFI();  /* Enter sleep — woken by DMA interrupt on completion */

        if (timeout_ms != 0) {
            elapsed_ms += poll_interval_ms;
            if (elapsed_ms >= timeout_ms) {
                printf("[CAMERA] WARNING: Capture timeout after %u ms.\r\n", elapsed_ms);
                return CAMERA_ERR_TIMEOUT;
            }
        }
    }

    return CAMERA_OK;
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
    /* OV7692 standby: set PWDN bit in COM2 register (0x09) */
    int ret = prv_ov7692_write_reg(0x09, 0x10);  /* COM2: power down */
    if (ret != 0) {
        printf("[CAMERA] ERROR: Failed to enter standby: %d\r\n", ret);
        return CAMERA_ERR_INIT;
    }
    printf("[CAMERA] Entered standby mode.\r\n");
    return CAMERA_OK;
}

camera_status_t camera_exit_standby(void)
{
    /* Clear PWDN bit to resume normal operation */
    int ret = prv_ov7692_write_reg(0x09, 0x00);  /* COM2: normal operation */
    if (ret != 0) {
        printf("[CAMERA] ERROR: Failed to exit standby: %d\r\n", ret);
        return CAMERA_ERR_INIT;
    }
    /* Allow AEC/AGC to stabilize after wake */
    MXC_Delay(MXC_DELAY_MSEC(30));
    printf("[CAMERA] Exited standby mode.\r\n");
    return CAMERA_OK;
}

/* ── Private Implementation ───────────────────────────────────────────────── */

/**
 * @brief  Write a single register to the OV7692 via I2C.
 *
 * @param  reg_addr   8-bit OV7692 register address.
 * @param  value      8-bit value to write.
 *
 * @return 0 on success, non-zero on I2C error.
 */
static int prv_ov7692_write_reg(uint8_t reg_addr, uint8_t value)
{
    /* Use the MSDK SCCB (I2C-compatible) camera write function.
     * MXC_CAMERA_WriteReg() sends: [SLAVE_ADDR_W][REG_ADDR][VALUE]
     * This function is provided by the MSDK camera library. */
    return MXC_CAMERA_WriteReg(OV7692_I2C_ADDR, reg_addr, value);
}

/**
 * @brief  Write a sequence of register/value pairs to the OV7692.
 *
 * @param  regs  Two-column array of {reg_addr, value}.
 *               Terminated by the sentinel entry {0xFF, 0xFF}.
 *
 * @return 0 on success, failing register address on error (non-zero).
 */
static int prv_ov7692_write_reg_sequence(const uint8_t regs[][2])
{
    int i = 0;
    while (regs[i][0] != 0xFF || regs[i][1] != 0xFF) {
        int ret = prv_ov7692_write_reg(regs[i][0], regs[i][1]);
        if (ret != 0) {
            printf("[CAMERA] I2C write failed at reg 0x%02X = 0x%02X, err=%d\r\n",
                   regs[i][0], regs[i][1], ret);
            return (int)regs[i][0];  /* Return failing register address */
        }
        /* Short delay between register writes for sensor stability */
        MXC_Delay(MXC_DELAY_USEC(100));
        i++;
    }
    return 0;  /* All writes successful */
}

/**
 * @brief  DMA completion callback (runs in interrupt context).
 *
 * @param  ch   DMA channel number that completed.
 * @param  err  Error code (0 = success, non-zero = error).
 */
static void prv_dma_done_handler(int ch, int err)
{
    (void)ch;  /* Suppress unused parameter warning */

    if (err != 0) {
        printf("[CAMERA] DMA error in completion handler: %d\r\n", err);
        /* Still mark as done so main loop doesn't hang */
    }

    /* Mark frame capture as complete */
    s_capture_done = true;

    /* Invoke user callback if registered */
    if (s_done_callback != NULL) {
        s_done_callback();
    }
}
