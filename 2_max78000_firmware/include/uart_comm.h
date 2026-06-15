/**
 * @file    uart_comm.h
 * @brief   UART Communication & Buzzer Control Interface.
 * @project Edge AI Palm Oil FFB (TBS) Grading System
 *
 * @details Handles JSON result formatting, UART transmission to the ESP-12E
 *          gateway, and buzzer control for anomaly alert signaling.
 *
 * @hardware
 *   UART Port: MXC_UART0 (TX=P0.1, RX=P0.0 on MAX78000FTHR)
 *   Baud Rate: 115200, 8N1 (8 data bits, no parity, 1 stop bit)
 *   Buzzer:    GPIO P0.12, LOW = ON (low-level trigger), HIGH = OFF
 *
 * @protocol
 *   JSON frame format: {"g":<grade>,"c":<confidence>}\n
 *   - "g": uint8, grade class index [0..3]
 *   - "c": uint8, confidence percentage [0..100]
 *   - "\n": newline delimiter for ESP-12E parser frame detection
 *   Example: {"g":1,"c":94}\n
 *   Max JSON string length: 20 bytes (well within a single UART FIFO burst)
 *
 * @buzzer_logic
 *   The buzzer module is a LOW-LEVEL trigger type:
 *   - GPIO LOW  → Buzzer ON  (alert active)
 *   - GPIO HIGH → Buzzer OFF (normal state)
 *   Triggers when: grade == CNN_CLASS_JANJANG_KOSONG (3) OR confidence < threshold
 */

#ifndef UART_COMM_H
#define UART_COMM_H

#include <stdint.h>
#include <stdbool.h>
#include "cnn_inference.h"

/* ── Configuration Constants ─────────────────────────────────────────────── */

/** UART baud rate for MAX78000 → ESP-12E link */
#define UART_COMM_BAUD_RATE             (115200U)

/**
 * @brief  Maximum length of the formatted JSON output string (including '\n').
 *         {"g":3,"c":100}\n = 16 chars + null = 17. Use 32 for safety margin.
 */
#define UART_COMM_JSON_MAX_LEN          (32U)

/**
 * @brief  Minimum confidence threshold percentage.
 *         If confidence falls below this, an anomaly alert is triggered
 *         regardless of the predicted class.
 */
#define UART_COMM_MIN_CONFIDENCE_PCT    (60U)

/**
 * @brief  Duration in milliseconds for a single buzzer alert pulse.
 *         Set to 500 ms (half-second beep) for clear audible warning.
 */
#define UART_COMM_BUZZER_PULSE_MS       (500U)

/* ── Error Codes ──────────────────────────────────────────────────────────── */

typedef enum {
    UART_COMM_OK            =  0,  /**< Success */
    UART_COMM_ERR_INIT      = -1,  /**< UART peripheral init failed */
    UART_COMM_ERR_TRANSMIT  = -2,  /**< UART TX error (FIFO overflow / busy) */
    UART_COMM_ERR_FORMAT    = -3,  /**< JSON formatting error */
    UART_COMM_ERR_NULL_PTR  = -4,  /**< Null pointer argument */
} uart_comm_status_t;

/* ── Public API ───────────────────────────────────────────────────────────── */

/**
 * @brief  Initialize UART0 peripheral and buzzer GPIO pin.
 *
 * @details Configures:
 *   - MXC_UART0 at UART_COMM_BAUD_RATE (115200) baud, 8N1 format.
 *   - TX/RX pins via MSDK GPIO alternate function MF (MAX Function).
 *   - Buzzer GPIO pin (P0.12) as output, set HIGH (buzzer OFF) initially.
 *
 * @note   Call once during system startup before any UART transmission.
 *
 * @return UART_COMM_OK on success, UART_COMM_ERR_INIT on failure.
 */
uart_comm_status_t uart_comm_init(void);

/**
 * @brief  Format CNN result into compact JSON and transmit over UART0.
 *
 * @details Builds a JSON string of the form: {"g":<grade>,"c":<confidence>}\n
 *          Then transmits it byte-by-byte over UART0 in a blocking loop.
 *          Additionally triggers the buzzer if anomaly conditions are met:
 *            - grade == CNN_CLASS_JANJANG_KOSONG (empty bunch), OR
 *            - confidence < UART_COMM_MIN_CONFIDENCE_PCT (uncertain result)
 *
 * @param[in] result  Pointer to cnn_result_t from the CNN inference module.
 *
 * @return UART_COMM_OK on success.
 *         UART_COMM_ERR_NULL_PTR if result is NULL.
 *         UART_COMM_ERR_FORMAT if snprintf fails.
 *         UART_COMM_ERR_TRANSMIT if UART write fails mid-transmission.
 */
uart_comm_status_t uart_send_result(const cnn_result_t *result);

/**
 * @brief  Transmit a raw null-terminated string over UART0.
 *
 * @details Utility function for debug/status messages. Uses blocking
 *          byte-by-byte transmission. For production use, prefer
 *          uart_send_result() for structured result output.
 *
 * @param[in] str  Null-terminated string to transmit.
 *
 * @return UART_COMM_OK on success, UART_COMM_ERR_TRANSMIT on error.
 */
uart_comm_status_t uart_send_string(const char *str);

/**
 * @brief  Activate the buzzer for a fixed pulse duration.
 *
 * @details Drives the buzzer GPIO pin LOW (active) for UART_COMM_BUZZER_PULSE_MS
 *          milliseconds, then drives it HIGH (inactive).
 *          This is a BLOCKING call — it uses MXC_Delay for the pulse duration.
 *
 * @note   The buzzer is a LOW-LEVEL trigger module:
 *           LOW  = buzzer ON
 *           HIGH = buzzer OFF
 */
void buzzer_trigger_alert(void);

/**
 * @brief  Immediately silence the buzzer (set GPIO HIGH).
 *
 * @details Useful for emergency stop or when a manual override is needed.
 */
void buzzer_force_off(void);

/**
 * @brief  Query whether the buzzer is currently active.
 *
 * @return true if buzzer GPIO is currently driven LOW (active).
 *         false if buzzer is OFF (GPIO HIGH).
 */
bool buzzer_is_active(void);

#endif /* UART_COMM_H */
