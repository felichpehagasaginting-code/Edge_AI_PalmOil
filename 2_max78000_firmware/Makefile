################################################################################
# FILE: Makefile
# PROJECT: Edge AI Palm Oil FFB (TBS) Grading System
# TARGET: MAX78000FTHR (ARM Cortex-M4F)
# TOOLCHAIN: ARM GCC (arm-none-eabi-gcc) via Maxim MSDK
#
# DESCRIPTION:
#   Build system for the MAX78000FTHR firmware. Integrates with the Maxim
#   Microcontrollers SDK (MSDK) build infrastructure.
#
# PREREQUISITES:
#   1. Install MSDK: https://github.com/analogdevicesinc/msdk
#      Default install path on Linux: ~/MaximSDK
#   2. Install ARM GCC toolchain (included with MSDK)
#   3. Set MSDK_PATH environment variable or update below
#
# USAGE:
#   make                   # Build firmware (debug mode)
#   make release           # Build firmware (optimized, no debug symbols)
#   make clean             # Remove build artifacts
#   make flash             # Flash firmware to MAX78000FTHR via OpenOCD
#   make flash-and-monitor # Flash and open serial monitor at 115200 baud
#   make size              # Print section sizes and memory usage report
#
# ENVIRONMENT VARIABLES:
#   MSDK_PATH   - Path to MSDK root (default: ~/MaximSDK)
#   TARGET      - Target device (default: MAX78000)
#   BOARD       - Board variant (default: FTHR_RevA for MAX78000FTHR)
################################################################################

# ── Target Hardware ────────────────────────────────────────────────────────────
TARGET      := MAX78000
BOARD       := FTHR_RevA

# ── Project Name (output binary prefix) ────────────────────────────────────────
PROJECT     := tbs_grader

# ── MSDK Path ──────────────────────────────────────────────────────────────────
# Update this to match your MSDK installation directory.
# Override from command line: make MSDK_PATH=/path/to/msdk
MSDK_PATH   ?= $(HOME)/MaximSDK

# Verify MSDK exists
ifeq ($(wildcard $(MSDK_PATH)),)
    $(error MSDK not found at $(MSDK_PATH). \
            Install from https://github.com/analogdevicesinc/msdk \
            or set MSDK_PATH= on the make command line.)
endif

# ── Toolchain (from MSDK) ──────────────────────────────────────────────────────
TOOLCHAIN_PATH := $(MSDK_PATH)/Tools/GNUTools/10.3/bin
CC   := $(TOOLCHAIN_PATH)/arm-none-eabi-gcc
CXX  := $(TOOLCHAIN_PATH)/arm-none-eabi-g++
AS   := $(TOOLCHAIN_PATH)/arm-none-eabi-gcc -x assembler-with-cpp
LD   := $(TOOLCHAIN_PATH)/arm-none-eabi-gcc
SIZE := $(TOOLCHAIN_PATH)/arm-none-eabi-size
OBJCOPY := $(TOOLCHAIN_PATH)/arm-none-eabi-objcopy
OBJDUMP := $(TOOLCHAIN_PATH)/arm-none-eabi-objdump

# ── MSDK Libraries & Drivers ───────────────────────────────────────────────────
MSDK_LIBS   := $(MSDK_PATH)/Libraries
CMSIS_DIR   := $(MSDK_LIBS)/CMSIS
PERIPH_DIR  := $(MSDK_LIBS)/PeriphDrivers
BOARD_DIR   := $(MSDK_LIBS)/Boards/$(TARGET)/$(BOARD)
CAMERA_LIB  := $(MSDK_LIBS)/Camera

# ── Source Files ───────────────────────────────────────────────────────────────
# Project source files
SRCS_C := \
    src/main.c          \
    src/camera.c        \
    src/preprocess.c    \
    src/cnn_inference.c \
    src/uart_comm.c     \
    cnn_generated/tbs_cnn.c

# MSDK source files required for MAX78000
SRCS_C += \
    $(PERIPH_DIR)/Source/SYS/mxc_sys.c               \
    $(PERIPH_DIR)/Source/GPIO/gpio_me17.c             \
    $(PERIPH_DIR)/Source/GPIO/gpio_common.c           \
    $(PERIPH_DIR)/Source/UART/uart_me17.c             \
    $(PERIPH_DIR)/Source/UART/uart_common.c           \
    $(PERIPH_DIR)/Source/DMA/dma_me17.c               \
    $(PERIPH_DIR)/Source/DMA/dma_common.c             \
    $(PERIPH_DIR)/Source/I2C/i2c_me17.c               \
    $(PERIPH_DIR)/Source/CNN/cnn_me17.c               \
    $(PERIPH_DIR)/Source/ICC/icc_me17.c               \
    $(PERIPH_DIR)/Source/LP/lp_me17.c                 \
    $(CAMERA_LIB)/camera.c                            \
    $(CAMERA_LIB)/ov7692.c                            \
    $(BOARD_DIR)/Source/board.c                       \
    $(BOARD_DIR)/Source/led.c                         \
    $(CMSIS_DIR)/Device/Maxim/$(TARGET)/Source/system_max78000.c

# Startup assembly file (device-specific reset handler)
SRCS_S := \
    $(CMSIS_DIR)/Device/Maxim/$(TARGET)/Source/GCC/startup_max78000.S

# ── Include Paths ──────────────────────────────────────────────────────────────
INCS := \
    -Iinclude                                                   \
    -Icnn_generated                                             \
    -I$(CMSIS_DIR)/Include                                      \
    -I$(CMSIS_DIR)/Device/Maxim/$(TARGET)/Include               \
    -I$(PERIPH_DIR)/Include/$(TARGET)                           \
    -I$(BOARD_DIR)/Include                                      \
    -I$(CAMERA_LIB)

# ── Compiler Flags ─────────────────────────────────────────────────────────────
# Architecture: ARM Cortex-M4F with hardware floating point (FPv4-SP)
ARCH_FLAGS := \
    -mcpu=cortex-m4        \
    -mthumb                \
    -mfpu=fpv4-sp-d16      \
    -mfloat-abi=hard

# Common compilation flags
CFLAGS_COMMON := \
    $(ARCH_FLAGS)          \
    -DTARGET=$(TARGET)     \
    -DTARGET_REV=0x4131    \
    -DBOARD_FTHR_RevA      \
    -DMX_DEVICE_MAX78000   \
    $(INCS)                \
    -Wall                  \
    -Wextra                \
    -Wno-unused-parameter  \
    -ffunction-sections    \
    -fdata-sections        \
    -std=gnu11

# Debug build flags (default target)
CFLAGS_DEBUG := $(CFLAGS_COMMON) \
    -DDEBUG                \
    -Og                    \
    -ggdb3

# Release build flags (optimized, no debug symbols)
CFLAGS_RELEASE := $(CFLAGS_COMMON) \
    -O2                    \
    -DNDEBUG

# Default to debug build
CFLAGS := $(CFLAGS_DEBUG)

# ── Linker Flags ───────────────────────────────────────────────────────────────
LINKER_SCRIPT := $(CMSIS_DIR)/Device/Maxim/$(TARGET)/Source/GCC/max78000.ld

LDFLAGS := \
    $(ARCH_FLAGS)          \
    -T $(LINKER_SCRIPT)    \
    -Wl,--gc-sections      \
    -Wl,-Map=$(BUILD_DIR)/$(PROJECT).map \
    -Wl,--print-memory-usage \
    --specs=nano.specs     \
    --specs=nosys.specs    \
    -lm

# ── Build Output Directory ─────────────────────────────────────────────────────
BUILD_DIR := build

# ── Object File Generation ─────────────────────────────────────────────────────
OBJS_C := $(addprefix $(BUILD_DIR)/, $(notdir $(SRCS_C:.c=.o)))
OBJS_S := $(addprefix $(BUILD_DIR)/, $(notdir $(SRCS_S:.S=.o)))
OBJS   := $(OBJS_C) $(OBJS_S)

# vpath: tell make where to find source files without full path in OBJS
vpath %.c $(sort $(dir $(SRCS_C)))
vpath %.S $(sort $(dir $(SRCS_S)))

# ── Build Targets ──────────────────────────────────────────────────────────────

.PHONY: all release clean flash flash-and-monitor size help

all: $(BUILD_DIR)/$(PROJECT).bin
	@echo ""
	@echo "Build complete: $(BUILD_DIR)/$(PROJECT).bin"
	@echo "Flash to device with: make flash"

release: CFLAGS := $(CFLAGS_RELEASE)
release: clean all
	@echo "Release build complete."

# ── ELF Linking ───────────────────────────────────────────────────────────────
$(BUILD_DIR)/$(PROJECT).elf: $(OBJS) | $(BUILD_DIR)
	@echo "[LD]  $@"
	$(LD) $(LDFLAGS) -o $@ $^

# ── Binary Conversion ─────────────────────────────────────────────────────────
$(BUILD_DIR)/$(PROJECT).bin: $(BUILD_DIR)/$(PROJECT).elf
	@echo "[BIN] $@"
	$(OBJCOPY) -O binary $< $@

$(BUILD_DIR)/$(PROJECT).hex: $(BUILD_DIR)/$(PROJECT).elf
	@echo "[HEX] $@"
	$(OBJCOPY) -O ihex $< $@

# ── C Compilation Rules ───────────────────────────────────────────────────────
$(BUILD_DIR)/%.o: %.c | $(BUILD_DIR)
	@echo "[CC]  $<"
	$(CC) $(CFLAGS) -c $< -o $@

# ── Assembly Compilation Rules ────────────────────────────────────────────────
$(BUILD_DIR)/%.o: %.S | $(BUILD_DIR)
	@echo "[AS]  $<"
	$(AS) $(CFLAGS) -c $< -o $@

# ── Create Build Directory ────────────────────────────────────────────────────
$(BUILD_DIR):
	mkdir -p $@

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	@echo "Removing build directory..."
	rm -rf $(BUILD_DIR)

# ── Size Report ───────────────────────────────────────────────────────────────
size: $(BUILD_DIR)/$(PROJECT).elf
	@echo ""
	@echo "=== Memory Usage Report ==="
	$(SIZE) --format=berkeley $<
	@echo ""
	@echo "MAX78000 Memory Limits:"
	@echo "  Flash: 512 KB (used by code + weights + constants)"
	@echo "  SRAM:  128 KB (used by stack, heap, frame buffers)"
	@echo ""

# ── Flash via OpenOCD ─────────────────────────────────────────────────────────
# Requires OpenOCD (included in MSDK Tools) and a MAX32625PICO debugger
# connected to the MAX78000FTHR SWD port.
OPENOCD := $(MSDK_PATH)/Tools/OpenOCD/openocd
OPENOCD_CFG := $(MSDK_PATH)/Tools/OpenOCD/scripts/board/max78000_fthr.cfg

flash: $(BUILD_DIR)/$(PROJECT).bin
	@echo "Flashing $(PROJECT).bin to MAX78000FTHR..."
	$(OPENOCD) \
	    -f $(OPENOCD_CFG) \
	    -c "program $(BUILD_DIR)/$(PROJECT).elf verify reset exit"

flash-and-monitor: flash
	@echo "Opening serial monitor at 115200 baud..."
	@echo "(Press Ctrl+A then Ctrl+X to exit picocom)"
	picocom -b 115200 /dev/ttyUSB0

# ── Help ──────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "TBS FFB Grader Firmware — Build System"
	@echo "======================================="
	@echo "Targets:"
	@echo "  all              : Build debug firmware (default)"
	@echo "  release          : Build release firmware (optimized)"
	@echo "  clean            : Remove build artifacts"
	@echo "  flash            : Flash firmware via OpenOCD"
	@echo "  flash-and-monitor: Flash + open picocom serial monitor"
	@echo "  size             : Print memory usage report"
	@echo ""
	@echo "Variables:"
	@echo "  MSDK_PATH=<path> : Path to Maxim MSDK (default: ~/MaximSDK)"
	@echo ""
