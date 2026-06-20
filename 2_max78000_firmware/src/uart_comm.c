/**
 * @file    uart_comm.c
 * @brief   UART Communication & Buzzer Control Implementation.
 * @project Edge AI Palm Oil FFB (TBS) Grading System
 *
 * @details Formats CNN inference results as compact JSON, transmits them
 *          over UART0 to the ESP-12E gateway, and manages the buzzer GPIO
 *          for anomaly alerting (low-level trigger type).
 *
 * @hardware_pins (MAX78000FTHR)
 *   UART0 TX: P0.1 (Alt Function: UART0_TX)
 *   UART0 RX: P0.0 (Alt Function: UART0_RX)
 *   Buzzer:   P0.12 (GPIO Output, LOW=ON, HIGH=OFF)
 *
 * @json_protocol
 *   Format: {"g":<grade>,"c":<confidence>}\n
 *   Example: {"g":1,"c":94}\n
 *   Total max length: ~19 chars (grade 0-3, confidence 0-100)
 */

#include "../include/uart_comm.h"

/* MSDK HAL includes */
#include "mxc_device.h"
#include "uart.h"        /* MSDK UART driver */
#include "gpio.h"        /* MSDK GPIO driver */
#include "mxc_delay.h"   /* MXC_Delay() for buzzer pulse timing */
#include "mxc_errors.h"  /* E_NO_ERROR, E_OVERFLOW, etc. */

/* C standard library */
#include <stdio.h>
#include <string.h>
#include <stdarg.h>

/* ── Hardware Pin Definitions (MAX78000FTHR board-specific) ──────────────── */

/** UART0 peripheral instance */
#define UART_COMM_PORT          MXC_UART0

/**
 * @brief  Buzzer GPIO configuration.
 *         P0.12 on MAX78000FTHR — verify against your schematic.
 *         Low-level trigger: drive LOW to activate buzzer.
 */
#define BUZZER_GPIO_PORT        MXC_GPIO0
#define BUZZER_GPIO_PIN         MXC_GPIO_PIN_12
#define BUZZER_GPIO_FUNC        MXC_GPIO_FUNC_OUT
#define BUZZER_GPIO_PAD         MXC_GPIO_PAD_NONE
#define BUZZER_ACTIVE_STATE     MXC_GPIO_OUT_LOW    /* LOW = buzzer ON */
#define BUZZER_IDLE_STATE       MXC_GPIO_OUT_HIGH   /* HIGH = buzzer OFF */

/* ── Private State ────────────────────────────────────────────────────────── */

/** Tracks whether uart_comm_init() succeeded */
static bool s_uart_initialized = false;

/** Tracks current buzzer state */
static volatile bool s_buzzer_active = false;

/* ── Private Helper: Send one byte over UART ─────────────────────────────── */

/**
 * @brief  Transmit a single byte over UART0 (blocking).
 *
 * @param  byte  The byte to transmit.
 * @return 0 on success, non-zero on UART FIFO error.
 */
static int prv_uart_send_byte(uint8_t byte)
{
    /* MXC_UART_WriteCharacter() pushes one byte into the TX FIFO.
     * If the FIFO is full, it blocks until space is available.
     * Returns E_NO_ERROR (0) on success. */
    return MXC_UART_WriteCharacter(UART_COMM_PORT, byte);
}

/* ── Public API Implementation ────────────────────────────────────────────── */

uart_comm_status_t uart_comm_init(void)
{
    int ret;

    /* ── UART0 Initialization ─────────────────────────────────────────────── */
    printf("[UART] Initializing UART0 at %u baud...\r\n", UART_COMM_BAUD_RATE);

    /*
     * MXC_UART_Init() configures:
     *   - Baud rate generator registers for the target baud rate
     *   - Frame format: 8 data bits, no parity, 1 stop bit (8N1)
     *   - TX/RX pin alternate functions (MSDK handles pin mux internally)
     *   - UART peripheral clock enable
     *
     * Parameters:
     *   uart:     UART peripheral instance (MXC_UART0)
     *   baud:     Target baud rate (115200)
     *   map:      Pin mapping (MAP_A = default pins on MAX78000FTHR)
     */
    ret = MXC_UART_Init(UART_COMM_PORT, UART_COMM_BAUD_RATE, MXC_UART_IBRO_CLK);
    if (ret != E_NO_ERROR) {
        printf("[UART] ERROR: MXC_UART_Init failed: %d\r\n", ret);
        return UART_COMM_ERR_INIT;
    }

    /*
     * Set UART character length to 8 bits explicitly.
     * MXC_UART_Init may default to a different length on some MSDK versions.
     */
    ret = MXC_UART_SetDataSize(UART_COMM_PORT, 8);
    if (ret != E_NO_ERROR) {
        printf("[UART] WARNING: SetDataSize failed: %d (may be unsupported)\r\n", ret);
    }

    /* Flush TX and RX FIFOs to start clean */
    MXC_UART_ClearTXFIFO(UART_COMM_PORT);
    MXC_UART_ClearRXFIFO(UART_COMM_PORT);

    /* ── Buzzer GPIO Initialization ──────────────────────────────────────── */
    printf("[UART] Initializing buzzer GPIO pin P0.%u...\r\n",
           __builtin_ctz(BUZZER_GPIO_PIN));  /* ctz = count trailing zeros → pin number */

    mxc_gpio_cfg_t buzzer_gpio_cfg = {
        .port   = BUZZER_GPIO_PORT,
        .mask   = BUZZER_GPIO_PIN,
        .func   = BUZZER_GPIO_FUNC,
        .pad    = BUZZER_GPIO_PAD,
        .vssel  = MXC_GPIO_VSSEL_VDDIO  /* Use VDDIO (3.3V) drive level */
    };

    ret = MXC_GPIO_Config(&buzzer_gpio_cfg);
    if (ret != E_NO_ERROR) {
        printf("[UART] ERROR: Buzzer GPIO config failed: %d\r\n", ret);
        return UART_COMM_ERR_INIT;
    }

    /* Initialize buzzer to OFF state (drive HIGH for low-level trigger) */
    MXC_GPIO_OutSet(BUZZER_GPIO_PORT, BUZZER_GPIO_PIN);
    s_buzzer_active = false;

    s_uart_initialized = true;
    printf("[UART] UART0 and buzzer GPIO initialized successfully.\r\n");

    return UART_COMM_OK;
}

uart_comm_status_t uart_send_result(const cnn_result_t *result)
{
    if (result == NULL) {
        return UART_COMM_ERR_NULL_PTR;
    }

    if (!s_uart_initialized) {
        return UART_COMM_ERR_INIT;
    }

    /* ── Check Anomaly Conditions → Trigger Buzzer ───────────────────────── */
    bool is_anomaly = false;

    if (result->grade == CNN_CLASS_BUSUK) {
        /* Busuk (rotten) detected — reject immediately */
        is_anomaly = true;
        printf("[UART] ALERT: Busuk (Rotten) detected!\r\n");
    }

    if (result->grade == CNN_CLASS_JANGKOS) {
        /* Jangkos (empty bunch) detected — potential conveyor feeding error */
        is_anomaly = true;
        printf("[UART] ALERT: Jangkos (Empty Bunch) detected!\r\n");
    }

    if (result->confidence_pct < UART_COMM_MIN_CONFIDENCE_PCT) {
        /* Low confidence — model is uncertain — may indicate contamination
         * or a bunch orientation that was not well represented in training */
        is_anomaly = true;
        printf("[UART] ALERT: Low confidence (%u%%) — anomaly flagged.\r\n",
               result->confidence_pct);
    }

    if (is_anomaly) {
        buzzer_trigger_alert();
    }

    /* ── Format JSON String ───────────────────────────────────────────────── */
    /*
     * Target format: {"g":<grade>,"c":<confidence>}\n
     * Grade: 0-3 (1 digit)
     * Confidence: 0-100 (up to 3 digits)
     * Total max characters: {"g":3,"c":100}\n = 18 chars + null = 19
     */
    char json_buf[UART_COMM_JSON_MAX_LEN];
    int  json_len;

    json_len = snprintf(
        json_buf,
        sizeof(json_buf),
        "{\"g\":%u,\"c\":%u}\n",
        (unsigned int)result->grade,
        (unsigned int)result->confidence_pct
    );

    /* Verify snprintf succeeded and didn't truncate */
    if (json_len <= 0 || json_len >= (int)sizeof(json_buf)) {
        printf("[UART] ERROR: JSON formatting failed (len=%d).\r\n", json_len);
        return UART_COMM_ERR_FORMAT;
    }

    /* ── Transmit JSON over UART0 ─────────────────────────────────────────── */
    for (int i = 0; i < json_len; i++) {
        int ret = prv_uart_send_byte((uint8_t)json_buf[i]);
        if (ret != E_NO_ERROR) {
            printf("[UART] ERROR: UART TX failed at byte %d (char='%c'): %d\r\n",
                   i, json_buf[i], ret);
            return UART_COMM_ERR_TRANSMIT;
        }
    }

    printf("[UART] Sent: %.*s", json_len, json_buf);  /* Log without double newline */

    return UART_COMM_OK;
}

uart_comm_status_t uart_send_string(const char *str)
{
    if (str == NULL) {
        return UART_COMM_ERR_NULL_PTR;
    }

    if (!s_uart_initialized) {
        return UART_COMM_ERR_INIT;
    }

    /* Transmit each character until null terminator */
    const char *ptr = str;
    while (*ptr != '\0') {
        int ret = prv_uart_send_byte((uint8_t)*ptr);
        if (ret != E_NO_ERROR) {
            return UART_COMM_ERR_TRANSMIT;
        }
        ptr++;
    }

    return UART_COMM_OK;
}

void buzzer_trigger_alert(void)
{
    if (s_buzzer_active) {
        /* Buzzer already on — don't restart timer, let current pulse finish */
        return;
    }

    s_buzzer_active = true;

    /* Drive GPIO LOW to activate the LOW-LEVEL trigger buzzer module */
    MXC_GPIO_OutClr(BUZZER_GPIO_PORT, BUZZER_GPIO_PIN);  /* LOW = ON */

    printf("[BUZZER] Alert activated! Pulse duration: %u ms.\r\n",
           UART_COMM_BUZZER_PULSE_MS);

    /* Block for the buzzer pulse duration.
     * UART_COMM_BUZZER_PULSE_MS = 500 ms (half-second audible beep).
     *
     * Note: This is a blocking delay. In a more advanced implementation,
     * use a hardware timer interrupt to de-activate the buzzer asynchronously
     * so the main pipeline can continue while the buzzer sounds. */
    MXC_Delay(MXC_DELAY_MSEC(UART_COMM_BUZZER_PULSE_MS));

    /* Drive GPIO HIGH to deactivate the buzzer */
    MXC_GPIO_OutSet(BUZZER_GPIO_PORT, BUZZER_GPIO_PIN);  /* HIGH = OFF */

    s_buzzer_active = false;
    printf("[BUZZER] Alert deactivated.\r\n");
}

void buzzer_force_off(void)
{
    /* Immediately set GPIO HIGH to silence the buzzer */
    MXC_GPIO_OutSet(BUZZER_GPIO_PORT, BUZZER_GPIO_PIN);
    s_buzzer_active = false;
    printf("[BUZZER] Force OFF command received.\r\n");
}

bool buzzer_is_active(void)
{
    return s_buzzer_active;
}
