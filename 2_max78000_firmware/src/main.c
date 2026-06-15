/**
 * @file    main.c
 * @brief   Central Application Control Loop — Edge AI FFB Grading System.
 * @project Edge AI Palm Oil FFB (TBS) Grading System
 * @target  Analog Devices MAX78000FTHR (ARM Cortex-M4F + CNN Accelerator)
 *
 * @overview
 *   This is the top-level firmware entry point. It orchestrates the complete
 *   scan-grade-report pipeline triggered by a photoelectric proximity sensor
 *   on the palm oil conveyor belt.
 *
 * @state_machine
 *
 *   ┌─────────────────────────────────────────────────────────────┐
 *   │                    SYSTEM STARTUP                           │
 *   │  1. Configure system clock (100 MHz)                        │
 *   │  2. Initialize: UART, Camera, CNN HW, modules               │
 *   │  3. Configure proximity sensor GPIO interrupt               │
 *   └──────────────────────────┬──────────────────────────────────┘
 *                              │
 *                              ▼
 *   ┌─────────────────────────────────────────────────────────────┐
 *   │                 IDLE / LOW POWER SLEEP                      │
 *   │         CPU in WFI (Wait For Interrupt) state               │
 *   │         CNN accelerator: clock-gated, ~0.1 mW               │
 *   │         Camera: standby mode, ~0.5 mA                       │
 *   └──────────────────────────┬──────────────────────────────────┘
 *                              │ GPIO IRQ (proximity sensor trigger)
 *                              ▼
 *   ┌─────────────────────────────────────────────────────────────┐
 *   │                  SCAN PIPELINE                              │
 *   │  Step 1: Camera wake + DMA frame capture (non-blocking)     │
 *   │  Step 2: Wait for DMA completion (WFI-based)                │
 *   │  Step 3: Preprocess: RGB565 → INT8 + contrast enhance       │
 *   │  Step 4: CNN HW: load input → start → wait → get result     │
 *   │  Step 5: UART: format JSON → transmit → buzzer if anomaly   │
 *   └──────────────────────────┬──────────────────────────────────┘
 *                              │ Pipeline complete
 *                              └──────────► Back to IDLE
 *
 * @irq_source
 *   GPIO interrupt on: P0.14 (configurable — see PROXIMITY_GPIO_PIN)
 *   Connected to: Photoelectric proximity sensor (NPN, active-LOW output)
 *   Trigger edge: FALLING (sensor output goes LOW when object detected)
 *
 * @power_profile
 *   Idle:      ~0.5 mA  (core in WFI, camera standby, CNN clock-gated)
 *   Scanning:  ~50 mA   (core active, camera streaming, CNN running)
 *   Alert:     +5 mA    (buzzer energized)
 */

#include <stdio.h>
#include <string.h>
#include <stdbool.h>

/* MSDK system includes */
#include "mxc_device.h"
#include "mxc_sys.h"
#include "mxc_delay.h"
#include "nvic_table.h"
#include "gpio.h"
#include "led.h"          /* On-board LED for status indication */

/* Project module includes */
#include "../include/camera.h"
#include "../include/preprocess.h"
#include "../include/cnn_inference.h"
#include "../include/uart_comm.h"

/* ── GPIO Configuration for Photoelectric Proximity Sensor ──────────────── */

/**
 * @brief  GPIO port and pin for the photoelectric proximity sensor trigger.
 *         Connect the sensor's NPN open-collector output to this pin.
 *         Use a 10kΩ pull-up resistor to VDDIO (3.3V).
 *
 *         Wiring for Flying Fish MH-MQ Photoelectric Sensor:
 *           Sensor VCC  → MAX78000 3.3V
 *           Sensor GND  → MAX78000 GND
 *           Sensor DO   → MAX78000 P0.14 (with 10kΩ pull-up to 3.3V)
 */
#define PROXIMITY_GPIO_PORT     MXC_GPIO0
#define PROXIMITY_GPIO_PIN      MXC_GPIO_PIN_14
#define PROXIMITY_GPIO_FUNC     MXC_GPIO_FUNC_IN
#define PROXIMITY_GPIO_PAD      MXC_GPIO_PAD_PULL_UP  /* Internal pull-up */

/**
 * @brief  Status LED assignment.
 *         LED0 = scanning indicator (blinks on each scan)
 *         LED1 = error indicator (stays on if init fails)
 *         MAX78000FTHR has 2 on-board LEDs (red and green).
 */
#define LED_SCAN_INDICATOR      0   /* LED0: Green — scan in progress */
#define LED_ERROR_INDICATOR     1   /* LED1: Red — system error */

/* ── Private State ────────────────────────────────────────────────────────── */

/**
 * @brief  Flag set by the GPIO ISR to signal a conveyor object detection.
 *         Checked in the main loop — not processed in ISR to keep ISR minimal.
 *         Declared volatile: modified in ISR, read in main loop (different contexts).
 */
static volatile bool s_conveyor_trigger_pending = false;

/**
 * @brief  CNN input tensor buffer (HWC format, INT8).
 *         Size: 128 * 128 * 3 = 49,152 bytes.
 *         Allocated statically here (main context) to avoid stack overflow.
 */
static int8_t s_cnn_input_buffer[PREPROCESS_CNN_INPUT_SIZE];

/**
 * @brief  CNN inference result structure — populated each scan cycle.
 */
static cnn_result_t s_inference_result;

/**
 * @brief  Scan counter — total bunches processed since boot.
 *         Transmitted in debug output for production traceability.
 */
static uint32_t s_total_scans = 0;

/* ── Private Function Declarations ───────────────────────────────────────── */

static void     prv_system_init(void);
static void     prv_proximity_gpio_irq_init(void);
static void     prv_proximity_isr_handler(void *context);
static void     prv_run_scan_pipeline(void);
static void     prv_system_error_halt(const char *error_msg);

/* ── Entry Point ──────────────────────────────────────────────────────────── */

int main(void)
{
    /* ── Phase 1: System Initialization ─────────────────────────────────── */
    prv_system_init();

    /* ── Phase 2: Initialize All Modules ────────────────────────────────── */

    /* Init UART0 (115200 baud) and buzzer GPIO */
    uart_comm_status_t uart_ret = uart_comm_init();
    if (uart_ret != UART_COMM_OK) {
        LED_On(LED_ERROR_INDICATOR);
        /* Can't use UART to log since it failed — halt silently */
        while (1) { __WFI(); }
    }

    printf("\r\n");
    printf("=========================================\r\n");
    printf("  Edge AI Palm Oil FFB Grading System   \r\n");
    printf("  Target: MAX78000FTHR                  \r\n");
    printf("  Build: %s %s                          \r\n", __DATE__, __TIME__);
    printf("=========================================\r\n");

    /* Init OV7692 camera (sets up DVP + DMA + registers) */
    printf("[MAIN] Initializing camera module...\r\n");
    camera_status_t cam_ret = camera_module_init();
    if (cam_ret != CAMERA_OK) {
        prv_system_error_halt("[MAIN] FATAL: Camera init failed.");
    }

    /* Init MAX78000 CNN hardware accelerator + load weights */
    printf("[MAIN] Initializing CNN hardware accelerator...\r\n");
    cnn_status_t cnn_ret = cnn_hw_init();
    if (cnn_ret != CNN_OK) {
        prv_system_error_halt("[MAIN] FATAL: CNN hardware init failed.");
    }

    /* Configure the photoelectric proximity sensor GPIO interrupt */
    printf("[MAIN] Configuring proximity sensor GPIO interrupt...\r\n");
    prv_proximity_gpio_irq_init();

    /* ── Phase 3: Send Ready Notification to Gateway ─────────────────────── */
    uart_send_string("{\"status\":\"READY\",\"dev\":\"MAX78000\"}\n");

    printf("[MAIN] System ready. Waiting for conveyor trigger...\r\n");
    LED_On(LED_SCAN_INDICATOR);     /* Solid green = system ready */
    MXC_Delay(MXC_DELAY_MSEC(100));
    LED_Off(LED_SCAN_INDICATOR);    /* Blink off — entering idle */

    /* ── Phase 4: Main Event Loop ────────────────────────────────────────── */
    /*
     * The system spends the vast majority of time here in low-power sleep.
     * Power consumption in WFI: ~0.5 mA (mostly camera standby and LDO quiescent).
     *
     * When the photoelectric sensor detects a palm oil bunch on the conveyor,
     * it drives the GPIO pin LOW (NPN open-collector), triggering the GPIO IRQ.
     * The ISR sets s_conveyor_trigger_pending = true and returns immediately.
     * The main loop wakes from WFI, checks the flag, and executes the pipeline.
     */
    while (1) {
        /* Enter ARM sleep mode — CPU halts, peripherals remain active.
         * Wake sources: any pending IRQ (GPIO sensor, SysTick, DMA, etc.) */
        __WFI();

        /* Check if the conveyor sensor fired */
        if (s_conveyor_trigger_pending) {
            /* Clear the flag immediately to avoid re-triggering */
            s_conveyor_trigger_pending = false;

            /* Execute the full scan-grade-report pipeline */
            prv_run_scan_pipeline();
        }
        /* If woken by another IRQ (SysTick, etc.), simply loop back to sleep */
    }

    /* Unreachable — embedded systems loop forever */
    return 0;
}

/* ── Private Function Implementations ────────────────────────────────────── */

/**
 * @brief  Configure MAX78000 system clocks and core peripherals.
 *
 * @details Sets the system clock to 100 MHz (IPO oscillator).
 *          Enables SysTick for MXC_Delay functionality.
 *          Enables FPU for Cortex-M4F floating point (used during printf).
 */
static void prv_system_init(void)
{
    /*
     * MXC_SYS_Clock_Select() configures the core clock.
     * MXC_S_GCR_CLKCTRL_CLKSEL_IPO = Internal Primary Oscillator (100 MHz).
     * This is the maximum clock speed on MAX78000.
     */
    MXC_SYS_Clock_Select(MXC_SYS_CLOCK_IPO);

    /*
     * Update SystemCoreClock variable (CMSIS requirement).
     * This ensures MXC_Delay and other timing functions use the correct clock.
     */
    SystemCoreClockUpdate();

    /*
     * Enable the FPU (Floating Point Unit) on Cortex-M4F.
     * Required if any code uses float/double operations.
     * The CNN inference uses only integer arithmetic, but printf may use float.
     */
    __enable_irq();  /* Enable global interrupts */

    /* Initialize on-board LEDs for status indication */
    LED_Init();
    LED_Off(LED_SCAN_INDICATOR);
    LED_Off(LED_ERROR_INDICATOR);

    printf("[MAIN] System clock: %lu Hz\r\n", (unsigned long)SystemCoreClock);
}

/**
 * @brief  Configure the photoelectric proximity sensor GPIO pin and interrupt.
 *
 * @details Configures P0.14 as a GPIO input with internal pull-up resistor.
 *          Enables a FALLING-edge interrupt (sensor output: HIGH=no object,
 *          LOW=object detected → falling edge = detection event).
 *
 *          The GPIO interrupt is routed through the MXC NVIC to the ISR
 *          registered via MXC_GPIO_RegisterCallback().
 */
static void prv_proximity_gpio_irq_init(void)
{
    /* Configure GPIO pin as input with pull-up */
    mxc_gpio_cfg_t proximity_cfg = {
        .port   = PROXIMITY_GPIO_PORT,
        .mask   = PROXIMITY_GPIO_PIN,
        .func   = PROXIMITY_GPIO_FUNC,
        .pad    = PROXIMITY_GPIO_PAD,   /* Internal pull-up for NPN open-collector */
        .vssel  = MXC_GPIO_VSSEL_VDDIO
    };

    int ret = MXC_GPIO_Config(&proximity_cfg);
    if (ret != E_NO_ERROR) {
        prv_system_error_halt("[MAIN] FATAL: Proximity GPIO config failed.");
    }

    /*
     * Configure the interrupt trigger condition.
     * MXC_GPIO_IntConfig() sets the interrupt to fire on:
     *   MXC_GPIO_INT_FALLING — sensor NPN output goes LOW (object detected)
     */
    ret = MXC_GPIO_IntConfig(&proximity_cfg, MXC_GPIO_INT_FALLING);
    if (ret != E_NO_ERROR) {
        prv_system_error_halt("[MAIN] FATAL: Proximity GPIO IntConfig failed.");
    }

    /*
     * Register the ISR callback function.
     * The MSDK GPIO driver calls this function from the GPIO IRQ handler.
     * Context parameter (NULL) is passed through — not used in our ISR.
     */
    MXC_GPIO_RegisterCallback(&proximity_cfg, prv_proximity_isr_handler, NULL);

    /* Enable the GPIO interrupt in the NVIC */
    MXC_GPIO_EnableInt(PROXIMITY_GPIO_PORT, PROXIMITY_GPIO_PIN);

    /* Set interrupt priority — use mid-priority so UART/DMA ISRs can preempt */
    NVIC_SetPriority(MXC_GPIO_GET_IRQ(MXC_GPIO_GET_IDX(PROXIMITY_GPIO_PORT)), 4);
    NVIC_EnableIRQ(MXC_GPIO_GET_IRQ(MXC_GPIO_GET_IDX(PROXIMITY_GPIO_PORT)));

    printf("[MAIN] Proximity sensor IRQ configured on GPIO P0.%u (FALLING edge).\r\n",
           __builtin_ctz(PROXIMITY_GPIO_PIN));
}

/**
 * @brief  GPIO ISR handler for the photoelectric proximity sensor.
 *
 * @details Called from the GPIO interrupt context when the sensor detects
 *          an object on the conveyor belt.
 *
 *          CRITICAL: Keep this ISR as short as possible.
 *          Only set the flag and return. All pipeline processing
 *          happens in the main loop after ISR returns.
 *
 * @param  context  Callback context pointer (unused, registered as NULL).
 */
static void prv_proximity_isr_handler(void *context)
{
    (void)context;  /* Suppress unused parameter warning */

    /*
     * Debounce guard: Check if a scan is already pending.
     * On a fast-moving conveyor, the sensor might trigger multiple times
     * as the bunch passes the sensor beam. We only want one scan per bunch.
     */
    if (!s_conveyor_trigger_pending) {
        s_conveyor_trigger_pending = true;
    }

    /* Clear the GPIO interrupt flag to prevent re-entry */
    MXC_GPIO_ClearFlags(PROXIMITY_GPIO_PORT, PROXIMITY_GPIO_PIN);
}

/**
 * @brief  Execute the complete scan-grade-report pipeline for one bunch.
 *
 * @details This function runs synchronously from the main loop context
 *          (not from an ISR). It performs:
 *            1. Camera wake + DMA frame capture
 *            2. Image preprocessing (RGB565 → INT8 + contrast)
 *            3. CNN hardware inference
 *            4. Result transmission via UART + buzzer alert if needed
 *
 *          Total pipeline latency budget:
 *            Camera wake:      ~30 ms
 *            Frame capture:    ~15 ms  (at ~30 fps)
 *            Preprocessing:    ~1  ms
 *            CNN inference:    ~5  ms
 *            UART TX:          ~2  ms  (20 bytes at 115200)
 *            Buzzer (if any):  ~500 ms
 *            TOTAL:            ~53 ms  (fast enough for typical conveyor speeds)
 */
static void prv_run_scan_pipeline(void)
{
    s_total_scans++;
    printf("\r\n[MAIN] === SCAN #%lu STARTED ===\r\n", (unsigned long)s_total_scans);

    /* Visual feedback: LED on during scan */
    LED_On(LED_SCAN_INDICATOR);

    /* ── Step 1: Wake Camera ─────────────────────────────────────────────── */
    camera_status_t cam_ret;

    cam_ret = camera_exit_standby();
    if (cam_ret != CAMERA_OK) {
        printf("[MAIN] WARNING: Camera exit standby failed: %d — proceeding.\r\n", cam_ret);
        /* Non-fatal: camera may already be awake from previous scan */
    }

    /* ── Step 2: Start DMA Frame Capture ─────────────────────────────────── */
    printf("[MAIN] Starting DMA camera capture...\r\n");

    cam_ret = camera_start_dma_capture();
    if (cam_ret != CAMERA_OK) {
        printf("[MAIN] ERROR: camera_start_dma_capture failed: %d\r\n", cam_ret);
        LED_Off(LED_SCAN_INDICATOR);
        return;  /* Abort this scan — wait for next trigger */
    }

    /* ── Step 3: Wait for DMA Completion (power-efficient WFI polling) ───── */
    cam_ret = camera_wait_capture_done(200 /* ms timeout */);
    if (cam_ret != CAMERA_OK) {
        printf("[MAIN] ERROR: Camera capture timeout.\r\n");
        LED_Off(LED_SCAN_INDICATOR);
        return;
    }
    printf("[MAIN] Camera capture complete.\r\n");

    /* ── Step 4: Put Camera Back to Standby ─────────────────────────────── */
    /* Immediately enter standby to save power during CNN computation */
    camera_enter_standby();

    /* ── Step 5: Image Preprocessing — RGB565 → INT8 ─────────────────────── */
    printf("[MAIN] Preprocessing: RGB565 → INT8 normalization...\r\n");

    const uint8_t *raw_frame = camera_get_frame_buffer();
    if (raw_frame == NULL) {
        printf("[MAIN] ERROR: camera_get_frame_buffer() returned NULL.\r\n");
        LED_Off(LED_SCAN_INDICATOR);
        return;
    }

    preprocess_status_t prep_ret;

    /* Convert RGB565 pixel data to INT8 HWC tensor */
    prep_ret = preprocess_normalize_to_int8(raw_frame, s_cnn_input_buffer);
    if (prep_ret != PREPROCESS_OK) {
        printf("[MAIN] ERROR: preprocess_normalize_to_int8 failed: %d\r\n", prep_ret);
        LED_Off(LED_SCAN_INDICATOR);
        return;
    }

    /* Apply local contrast enhancement for LED lighting variation */
    prep_ret = preprocess_contrast_enhance(s_cnn_input_buffer);
    if (prep_ret != PREPROCESS_OK) {
        printf("[MAIN] WARNING: contrast_enhance failed: %d — using raw tensor.\r\n", prep_ret);
        /* Non-fatal — continue with un-enhanced tensor */
    }
    printf("[MAIN] Preprocessing complete.\r\n");

    /* ── Step 6: Load Input into CNN Hardware SRAM ───────────────────────── */
    cnn_status_t cnn_ret;

    cnn_ret = cnn_load_input(s_cnn_input_buffer);
    if (cnn_ret != CNN_OK) {
        printf("[MAIN] ERROR: cnn_load_input failed: %d\r\n", cnn_ret);
        LED_Off(LED_SCAN_INDICATOR);
        return;
    }

    /* ── Step 7: Run CNN Hardware Inference ──────────────────────────────── */
    printf("[MAIN] Starting CNN hardware inference...\r\n");

    cnn_ret = cnn_start_and_wait();
    if (cnn_ret != CNN_OK) {
        printf("[MAIN] ERROR: CNN inference failed: %d\r\n", cnn_ret);
        LED_Off(LED_SCAN_INDICATOR);
        return;
    }

    /* ── Step 8: Extract Result — Argmax + Confidence ────────────────────── */
    cnn_ret = cnn_get_result(&s_inference_result);
    if (cnn_ret != CNN_OK) {
        printf("[MAIN] ERROR: cnn_get_result failed: %d\r\n", cnn_ret);
        LED_Off(LED_SCAN_INDICATOR);
        return;
    }

    /* ── Step 9: Transmit JSON Result to ESP-12E Gateway ─────────────────── */
    printf("[MAIN] Sending result to ESP-12E gateway...\r\n");

    uart_comm_status_t uart_ret = uart_send_result(&s_inference_result);
    if (uart_ret != UART_COMM_OK) {
        printf("[MAIN] ERROR: uart_send_result failed: %d\r\n", uart_ret);
        /* Non-fatal — data loss for this scan, but system continues */
    }

    /* ── Step 10: Pipeline Complete ──────────────────────────────────────── */
    printf("[MAIN] === SCAN #%lu COMPLETE | Grade=%u (%s) | Confidence=%u%% ===\r\n",
           (unsigned long)s_total_scans,
           s_inference_result.grade,
           cnn_get_class_name(s_inference_result.grade),
           s_inference_result.confidence_pct);

    LED_Off(LED_SCAN_INDICATOR);

    /*
     * Note: We deliberately do NOT call cnn_hw_disable() here.
     * Keeping CNN enabled between scans saves the ~1 ms weight reload latency
     * and is preferable for conveyor belts operating at >1 bunch/second rates.
     * Disable CNN only during prolonged idle periods (e.g., end of shift).
     */
}

/**
 * @brief  Halt the system on a fatal unrecoverable error.
 *
 * @param  error_msg  Null-terminated error description string.
 *
 * @details Prints the error over UART (best-effort), turns on the error LED,
 *          and enters an infinite loop. The watchdog timer (if configured)
 *          will eventually reset the MCU. In production, integrate with a
 *          hardware watchdog for automatic recovery.
 */
static void prv_system_error_halt(const char *error_msg)
{
    /* Best-effort UART output (may fail if UART init itself failed) */
    if (error_msg != NULL) {
        /* Use direct low-level UART write in case our UART module is not up */
        /* Writing direct to MSDK UART peripheral bypass */
        printf("%s\r\n", error_msg);
    }

    /* Turn on error LED */
    LED_On(LED_ERROR_INDICATOR);
    LED_Off(LED_SCAN_INDICATOR);

    printf("[MAIN] SYSTEM HALTED. Manual power cycle required.\r\n");

    /* Infinite loop — watchdog will reset after WDT timeout if configured */
    while (1) {
        /* Blink error LED at 1 Hz to indicate fault */
        LED_Toggle(LED_ERROR_INDICATOR);
        MXC_Delay(MXC_DELAY_MSEC(500));
    }
}
