#!/usr/bin/env bash
###############################################################################
# FILE: train_pipeline.sh
# PROJECT: Edge AI Palm Oil FFB (TBS) Grading System
# DESCRIPTION:
#   Two-phase training pipeline for the TBSClassifier CNN model targeting
#   the Analog Devices MAX78000 hardware CNN accelerator.
#
#   Phase 1: Standard float32 pre-training with QAT warm-up
#   Phase 2: Strict 8-bit Quantization-Aware Training (QAT) fine-tuning
#
# PREREQUISITES:
#   1. Clone and set up the ai8x-training SDK:
#      git clone https://github.com/analogdevicesinc/ai8x-training.git
#      cd ai8x-training && pip install -r requirements.txt
#
#   2. Copy/symlink project files into the ai8x-training directory:
#      cp IoT_Grad_Scanner/1_ai_training/models/tbs_classifier.py \
#         ai8x-training/models/
#      cp IoT_Grad_Scanner/1_ai_training/dataset/tbs_dataset.py \
#         ai8x-training/datasets/
#      cp IoT_Grad_Scanner/1_ai_training/policies/qat_policy_8b.yaml \
#         ai8x-training/policies/
#
#   3. Set up dataset directory structure:
#      ai8x-training/data/TBSDataset/
#        ├── train/
#        │   ├── 0_mentah/
#        │   ├── 1_matang/
#        │   ├── 2_overripe/
#        │   └── 3_janjang_kosong/
#        └── val/
#            ├── 0_mentah/
#            ├── 1_matang/
#            ├── 2_overripe/
#            └── 3_janjang_kosong/
#
# USAGE:
#   cd /path/to/ai8x-training
#   bash /path/to/IoT_Grad_Scanner/1_ai_training/train_pipeline.sh
#
# OUTPUT:
#   logs/TBSClassifier/phase1/best.pth.tar  ← Float pre-trained checkpoint
#   logs/TBSClassifier/phase2/best.pth.tar  ← QAT fine-tuned checkpoint (DEPLOY THIS)
###############################################################################

set -euo pipefail  # Exit on error, undefined var, pipe failure

# ── Color-coded logging helpers ───────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'  # No Color

log_info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
log_ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
log_section() { echo -e "\n${BOLD}${CYAN}══════════════════════════════════════════${NC}"; \
                echo -e "${BOLD}${CYAN}  $*${NC}"; \
                echo -e "${BOLD}${CYAN}══════════════════════════════════════════${NC}"; }

# ── Environment Verification ──────────────────────────────────────────────────

log_section "Verifying Environment"

# Verify we are running from the ai8x-training SDK root
if [[ ! -f "train.py" ]]; then
    log_error "train.py not found! Run this script from the ai8x-training SDK root directory."
fi

# Check for required Python dependencies
python -c "import torch, torchvision" 2>/dev/null || \
    log_error "PyTorch not installed. Run: pip install -r requirements.txt"

python -c "import ai8x" 2>/dev/null || \
    log_error "ai8x module not found. Ensure you are in the ai8x-training SDK environment."

log_ok "Environment verified. PyTorch $(python -c 'import torch; print(torch.__version__)') detected."

# ── Configuration Variables ───────────────────────────────────────────────────

# Device selection: MAX78000 device code is 85
DEVICE="MAX78000"

# Dataset root path (relative to ai8x-training SDK root)
DATA_ROOT="./data"

# Model name — must match the factory function name in models/tbs_classifier.py
MODEL_NAME="tbs_classifier"

# Dataset class name — must match the class name in datasets/tbs_dataset.py
DATASET_NAME="TBSDataset"

# Output log directories
LOG_DIR_PHASE1="./logs/TBSClassifier/phase1"
LOG_DIR_PHASE2="./logs/TBSClassifier/phase2"

# Checkpoint filenames
PHASE1_CHECKPOINT="${LOG_DIR_PHASE1}/best.pth.tar"
PHASE2_CHECKPOINT="${LOG_DIR_PHASE2}/best.pth.tar"

# GPU selection (0 for single GPU, use 0,1 for multi-GPU)
GPU_ID="0"

# Number of CPU workers for DataLoader
NUM_WORKERS=8

# Create output directories
mkdir -p "${LOG_DIR_PHASE1}"
mkdir -p "${LOG_DIR_PHASE2}"

log_info "Model          : ${MODEL_NAME}"
log_info "Dataset        : ${DATASET_NAME}"
log_info "Phase 1 output : ${LOG_DIR_PHASE1}"
log_info "Phase 2 output : ${LOG_DIR_PHASE2}"

# ── PHASE 1: Float Pre-Training ───────────────────────────────────────────────
# Goal: Train the model in full float32 precision to converge on a good
#       set of weights. Uses cosine annealing LR scheduler.
#
# Hyperparameters rationale:
#   --epochs 200   : Sufficient for convergence on small-medium datasets
#   --lr 0.001     : Adam default, works well with BatchNorm models
#   --batch-size 32: Fits comfortably on a mid-range GPU (8 GB VRAM)
#   --weight-decay : L2 regularization to prevent overfitting on small dataset
#   --no-bias      : Disable biases in conv layers (saves HW memory)
# ─────────────────────────────────────────────────────────────────────────────

log_section "PHASE 1: Float32 Pre-Training"

python train.py \
    --device "${DEVICE}" \
    --model "${MODEL_NAME}" \
    --dataset "${DATASET_NAME}" \
    --data "${DATA_ROOT}" \
    --epochs 200 \
    --optimizer Adam \
    --lr 0.001 \
    --weight-decay 5e-4 \
    --batch-size 32 \
    --workers "${NUM_WORKERS}" \
    --gpus "${GPU_ID}" \
    --print-freq 10 \
    --save-sample 10 \
    --no-bias \
    --obj topk \
    --save-freq 10 \
    --out-dir "${LOG_DIR_PHASE1}" \
    2>&1 | tee "${LOG_DIR_PHASE1}/phase1_training.log"

# Verify checkpoint was created
if [[ ! -f "${PHASE1_CHECKPOINT}" ]]; then
    log_error "Phase 1 checkpoint not found at: ${PHASE1_CHECKPOINT}"
fi

log_ok "Phase 1 complete. Best checkpoint: ${PHASE1_CHECKPOINT}"

# Print final top-1 accuracy from Phase 1 log
PHASE1_BEST_ACC=$(grep -oP 'Best=\K[0-9.]+' "${LOG_DIR_PHASE1}/phase1_training.log" | tail -1)
log_info "Phase 1 Best Top-1 Accuracy: ${PHASE1_BEST_ACC}%"

# ── PHASE 2: QAT Fine-Tuning ──────────────────────────────────────────────────
# Goal: Fine-tune the float model with 8-bit QAT using the Distiller
#       compression schedule defined in policies/qat_policy_8b.yaml.
#       This teaches the model to be robust to quantization noise.
#
# Key differences from Phase 1:
#   --resume-from   : Load Phase 1 best checkpoint as starting point
#   --compress      : Apply QAT policy (activates after warm-up epochs)
#   --lr 0.0001     : 10x lower LR to preserve Phase 1 learned features
#   --epochs 100    : Fewer epochs needed — model is already converged
# ─────────────────────────────────────────────────────────────────────────────

log_section "PHASE 2: 8-bit QAT Fine-Tuning"

python train.py \
    --device "${DEVICE}" \
    --model "${MODEL_NAME}" \
    --dataset "${DATASET_NAME}" \
    --data "${DATA_ROOT}" \
    --epochs 100 \
    --optimizer Adam \
    --lr 0.0001 \
    --weight-decay 1e-5 \
    --batch-size 32 \
    --workers "${NUM_WORKERS}" \
    --gpus "${GPU_ID}" \
    --print-freq 10 \
    --save-sample 10 \
    --no-bias \
    --compress "./policies/qat_policy_8b.yaml" \
    --resume-from "${PHASE1_CHECKPOINT}" \
    --out-dir "${LOG_DIR_PHASE2}" \
    2>&1 | tee "${LOG_DIR_PHASE2}/phase2_qat_training.log"

# Verify QAT checkpoint was created
if [[ ! -f "${PHASE2_CHECKPOINT}" ]]; then
    log_error "Phase 2 QAT checkpoint not found at: ${PHASE2_CHECKPOINT}"
fi

log_ok "Phase 2 complete. QAT checkpoint: ${PHASE2_CHECKPOINT}"

PHASE2_BEST_ACC=$(grep -oP 'Best=\K[0-9.]+' "${LOG_DIR_PHASE2}/phase2_qat_training.log" | tail -1)
log_info "Phase 2 (QAT) Best Top-1 Accuracy: ${PHASE2_BEST_ACC}%"

# ── Post-Training Evaluation ──────────────────────────────────────────────────

log_section "Post-Training: Evaluation on Validation Set"

python train.py \
    --device "${DEVICE}" \
    --model "${MODEL_NAME}" \
    --dataset "${DATASET_NAME}" \
    --data "${DATA_ROOT}" \
    --evaluate \
    --resume-from "${PHASE2_CHECKPOINT}" \
    --gpus "${GPU_ID}" \
    2>&1 | tee "${LOG_DIR_PHASE2}/phase2_eval.log"

log_ok "Evaluation complete. See: ${LOG_DIR_PHASE2}/phase2_eval.log"

# ── Model Size Report ─────────────────────────────────────────────────────────

log_section "Weight Budget Report"

python -c "
import torch
import sys
sys.path.insert(0, '.')

# Load checkpoint and count parameters
ckpt = torch.load('${PHASE2_CHECKPOINT}', map_location='cpu')
state_dict = ckpt.get('state_dict', ckpt)

total_params = sum(v.numel() for v in state_dict.values())
size_bytes = total_params  # 1 byte per INT8 parameter
size_kb = size_bytes / 1024.0
limit_kb = 442.0

print(f'  Total INT8 parameters : {total_params:,}')
print(f'  Estimated weight size : {size_kb:.2f} KB')
print(f'  MAX78000 weight limit : {limit_kb:.2f} KB')
print(f'  Budget utilization    : {100.0*size_kb/limit_kb:.1f}%')
status = '✓ WITHIN BUDGET' if size_kb <= limit_kb else '✗ EXCEEDS — reduce model!'
print(f'  Status                : {status}')
"

# ── Final Summary ─────────────────────────────────────────────────────────────

log_section "Training Complete"
log_ok "Phase 1 checkpoint : ${PHASE1_CHECKPOINT}"
log_ok "Phase 2 (QAT) checkpoint : ${PHASE2_CHECKPOINT}"
log_info ""
log_info "NEXT STEP: Run ai8x-synthesis to convert the QAT checkpoint to C code."
log_info "See: 1_ai_training/README_synthesis.md for full instructions."
log_info ""
log_info "Quick synthesis command (after setting up ai8x-synthesis SDK):"
log_info ""
log_info "  cd /path/to/ai8x-synthesis"
log_info "  python ai8xize.py \\"
log_info "    --verbose \\"
log_info "    --test-dir ./tests \\"
log_info "    --prefix tbs_cnn \\"
log_info "    --checkpoint-file ${PHASE2_CHECKPOINT} \\"
log_info "    --config-file networks/tbs_classifier-hwc.yaml \\"
log_info "    --device MAX78000 \\"
log_info "    --compact-weights \\"
log_info "    --mexpress \\"
log_info "    --embedded-code \\"
log_info "    --display-checkpoint"
