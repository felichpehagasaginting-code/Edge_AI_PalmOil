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
MSDK_PATH   ?= $(HOME)/Felichs/msdk

# Verify MSDK exists
ifeq ($(wildcard $(MSDK_PATH)),)
    $(error MSDK not found at $(MSDK_PATH). \
            Install from https://github.com/analogdevicesinc/msdk \
            or set MSDK_PATH= on the make command line.)
endif

# ── Toolchain (from MSDK or system PATH) ───────────────────────────────────────
# Use system-wide arm-none-eabi-gcc if MSDK toolchain is not found.
TOOLCHAIN_PATH := $(wildcard $(HOME)/Felichs/gcc-arm-none-eabi-10.3-2021.10/bin $(MSDK_PATH)/Tools/GNUTools/10.3/bin)
ifneq ($(TOOLCHAIN_PATH),)
    PREFIX := $(TOOLCHAIN_PATH)/
else
    PREFIX := 
endif

CC   := $(PREFIX)arm-none-eabi-gcc
CXX  := $(PREFIX)arm-none-eabi-g++
AS   := $(PREFIX)arm-none-eabi-gcc -x assembler-with-cpp
LD   := $(PREFIX)arm-none-eabi-gcc
SIZE := $(PREFIX)arm-none-eabi-size
OBJCOPY := $(PREFIX)arm-none-eabi-objcopy
OBJDUMP := $(PREFIX)arm-none-eabi-objdump

# ── MSDK Libraries & Drivers ───────────────────────────────────────────────────
MSDK_LIBS   := $(MSDK_PATH)/Libraries
CMSIS_DIR   := $(MSDK_LIBS)/CMSIS
PERIPH_DIR  := $(MSDK_LIBS)/PeriphDrivers
BOARD_DIR   := $(MSDK_LIBS)/Boards/$(TARGET)/$(BOARD)
CAMERA_LIB  := $(MSDK_LIBS)/MiscDrivers/Camera

# ── Source Files ───────────────────────────────────────────────────────────────
# Project source files
SRCS_C := \
    src/main.c          \
    src/cam_ov7692.c    \
    src/preprocess.c    \
    src/cnn_inference.c \
    src/uart_comm.c     \
    cnn_generated/tbs_cnn.c

# MSDK source files required for MAX78000
SRCS_C += \
    $(PERIPH_DIR)/Source/SYS/sys_ai85.c               \
    $(PERIPH_DIR)/Source/SYS/pins_ai85.c              \
    $(PERIPH_DIR)/Source/GPIO/gpio_ai85.c             \
    $(PERIPH_DIR)/Source/GPIO/gpio_common.c           \
    $(PERIPH_DIR)/Source/GPIO/gpio_reva.c             \
    $(PERIPH_DIR)/Source/UART/uart_ai85.c             \
    $(PERIPH_DIR)/Source/UART/uart_common.c           \
    $(PERIPH_DIR)/Source/UART/uart_revb.c             \
    $(PERIPH_DIR)/Source/DMA/dma_me17.c               \
    $(PERIPH_DIR)/Source/DMA/dma_reva.c               \
    $(PERIPH_DIR)/Source/I2C/i2c_me17.c               \
    $(PERIPH_DIR)/Source/I2C/i2c_reva.c               \
    $(PERIPH_DIR)/Source/ICC/icc_me17.c               \
    $(PERIPH_DIR)/Source/ICC/icc_reva.c               \
    $(PERIPH_DIR)/Source/LP/lp_ai85.c                 \
    $(PERIPH_DIR)/Source/SYS/mxc_delay.c              \
    $(PERIPH_DIR)/Source/SYS/nvic_table.c             \
    $(PERIPH_DIR)/Source/SYS/mxc_lock.c               \
    $(PERIPH_DIR)/Source/PT/pt_ai85.c                 \
    $(PERIPH_DIR)/Source/PT/pt_reva.c                 \
    $(PERIPH_DIR)/Source/CAMERAIF/cameraif_ai85.c     \
    $(PERIPH_DIR)/Source/CAMERAIF/cameraif_reva.c     \
    $(CAMERA_LIB)/sccb.c                              \
    $(CAMERA_LIB)/camera.c                            \
    $(CAMERA_LIB)/ov7692.c                            \
    $(BOARD_DIR)/Source/board.c                       \
    $(MSDK_LIBS)/MiscDrivers/LED/led.c                 \
    $(MSDK_LIBS)/MiscDrivers/PushButton/pb.c           \
    $(MSDK_LIBS)/MiscDrivers/PMIC/max20303.c           \
    $(CMSIS_DIR)/Device/Maxim/$(TARGET)/Source/system_max78000.c \
    $(CMSIS_DIR)/Device/Maxim/$(TARGET)/Source/heap.c

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
    -I$(CAMERA_LIB)                                             \
    -I$(MSDK_LIBS)/MiscDrivers/LED                              \
    -I$(MSDK_LIBS)/MiscDrivers/Display                          \
    -I$(MSDK_LIBS)/MiscDrivers/Display/fonts                    \
    -I$(MSDK_LIBS)/MiscDrivers/Touchscreen                      \
    -I$(MSDK_LIBS)/MiscDrivers/PushButton                       \
    -I$(MSDK_LIBS)/MiscDrivers/PMIC                             \
    -I$(PERIPH_DIR)/Source/DMA                                  \
    -I$(PERIPH_DIR)/Source/I2C                                  \
    -I$(PERIPH_DIR)/Source/ICC                                  \
    -I$(PERIPH_DIR)/Source/GPIO                                 \
    -I$(PERIPH_DIR)/Source/UART                                 \
    -I$(PERIPH_DIR)/Source/SYS                                  \
    -I$(PERIPH_DIR)/Source/LP                                   \
    -I$(PERIPH_DIR)/Source/PT                                   \
    -I$(PERIPH_DIR)/Source/CAMERAIF

# ── Compiler Flags ─────────────────────────────────────────────────────────────
# Architecture: ARM Cortex-M4F with hardware floating point (FPv4-SP)
ARCH_FLAGS := \
    -mcpu=cortex-m4        \
    -mthumb                \
    -mfpu=fpv4-sp-d16      \
    -mfloat-abi=hard

# ── Debug / Emulation Flags ───────────────────────────────────────────────────
# Set to 1 to bypass physical camera sensor check (emulates with dummy frames).
# Set to 0 when physical OV7692 camera is connected to the board.
CAMERA_BYPASS ?= 1

# Common compilation flags
CFLAGS_COMMON := \
    $(ARCH_FLAGS)          \
    -DTARGET=$(TARGET)     \
    -DTARGET_REV=0x4131    \
    -DBOARD_FTHR_RevA      \
    -DMX_DEVICE_MAX78000   \
    -DCAMERA_BYPASS=$(CAMERA_BYPASS) \
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

# ── Build Output Directory ─────────────────────────────────────────────────────
BUILD_DIR := build

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

# ── Flash via DAPLink or OpenOCD ──────────────────────────────────────────────
# Detects if DAPLink drive is mounted for drag-and-drop copy flashing
DAPLINK_DIR := $(wildcard /run/media/$(USER)/DAPLINK /media/$(USER)/DAPLINK)
OPENOCD     := $(MSDK_PATH)/Tools/OpenOCD/openocd
OPENOCD_CFG := $(MSDK_PATH)/Tools/OpenOCD/scripts/board/max78000_fthr.cfg

# Detect serial port (prefer ttyACM over ttyUSB)
PORT ?= $(shell ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null | head -n 1)

flash: $(BUILD_DIR)/$(PROJECT).bin
	@if [ -n "$(DAPLINK_DIR)" ]; then \
	    echo "DAPLINK drive found at: $(DAPLINK_DIR)"; \
	    echo "Flashing $(PROJECT).bin via file copy..."; \
	    cp $(BUILD_DIR)/$(PROJECT).bin "$(DAPLINK_DIR)/"; \
	    sync; \
	    echo "Flash write complete! The board will reboot automatically."; \
	else \
	    echo "DAPLINK drive not found. Falling back to OpenOCD..."; \
	    $(OPENOCD) -f $(OPENOCD_CFG) -c "program $(BUILD_DIR)/$(PROJECT).elf verify reset exit"; \
	fi

flash-and-monitor: flash
	@if [ -z "$(PORT)" ]; then \
	    echo "Error: No serial port (/dev/ttyACM* or /dev/ttyUSB*) found."; \
	    exit 1; \
	fi; \
	echo "Opening serial monitor on $(PORT) at 115200 baud..." ; \
	echo "(Press Ctrl+A then Ctrl+X to exit picocom)" ; \
	picocom -b 115200 $(PORT)

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
