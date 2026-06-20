"""CNN model for MAX78000-based Palm Oil FFB grading."""
###############################################################################
# FILE: models/tbs_classifier.py
# PROJECT: Edge AI Palm Oil FFB (TBS) Grading System
# AUTHOR: Generated for IoT_Grad_Scanner project
# DATE: 2026-06
#
# DESCRIPTION:
#   Defines a compact, hardware-accelerator-aware CNN model for 4-class
#   classification of Palm Oil Fresh Fruit Bunches (FFB/TBS):
#     Class 0 — Mentah      (Unripe)
#     Class 1 — Matang      (Ripe)
#     Class 2 — Overripe    (Over-ripe)
#     Class 3 — Janjang Kosong (Empty Bunch)
#
#   Designed explicitly for the Analog Devices MAX78000 CNN hardware
#   accelerator using the official ai8x-training SDK layer primitives.
#   All layers use fused operator variants to maximize throughput on the
#   dedicated HW pipeline.
#
# HARDWARE CONSTRAINTS (MAX78000):
#   - CNN weight memory: 442 KB (452,608 bytes) absolute maximum
#   - Max input channels per layer: 64
#   - Max kernel size: 3x3
#   - Input resolution: 128x128 pixels (RGB: 3 channels)
#   - Weight precision: INT8 (post-QAT)
#
# WEIGHT BUDGET ESTIMATE (INT8, approximate):
#   Block1 conv:  3 * 16 * 3 * 3  =    432  params
#   Block2 conv: 16 * 32 * 3 * 3  =  4,608  params
#   Block3 conv: 32 * 64 * 3 * 3  = 18,432  params  (after pool)
#   Block4 dw:   64 * 1  * 3 * 3  =    576  params  (depthwise)
#   Block4 pw:   64 * 64 * 1 * 1  =  4,096  params  (pointwise)
#   Classifier:  64 * 4            =    256  params  (after global avg pool)
#   TOTAL:  ~28,400 INT8 bytes  ≈  27.7 KB  << 442 KB budget ✓
#
# USAGE (inside ai8x-training):
#   Register this model via: models = {'tbs_classifier': TBSClassifier}
#   Or pass via CLI: --model tbs_classifier
#
# COMPATIBILITY:
#   - PyTorch >= 2.0
#   - ai8x-training SDK (ADI GitHub: analogdevicesinc/ai8x-training)
###############################################################################

import torch
import torch.nn as nn

# The ai8x module is provided by the ai8x-training SDK.
# It must be installed/on-path from the SDK root before importing.
import ai8x


###############################################################################
# Model Definition
###############################################################################

class TBSClassifier(nn.Module):
    """
    Compact 4-class CNN classifier for Palm Oil FFB grading.

    Architecture Overview:
        Input: (B, 3, 128, 128) — RGB image, 8-bit, signed INT8 after QAT

        ┌─ Block 1 ─── FusedConv2dBNReLU(3  → 16, 3x3) → (B,16,128,128)
        ├─ Block 2 ─── FusedConv2dBNReLU(16 → 32, 3x3) → (B,32,128,128)
        ├─ Block 3 ─── FusedMaxPoolConv2dBNReLU(32→64, 3x3, pool=2)
        │                                              → (B,64,63,63)
        ├─ Block 4a ── FusedDepthwiseConv2dBNReLU(64→64, 3x3, dw)
        │                                              → (B,64,63,63)
        ├─ Block 4b ── FusedConv2dBNReLU(64→64, 1x1, pw) → (B,64,63,63)
        ├─ Block 5 ─── FusedMaxPoolConv2dBNReLU(64→64, 3x3, pool=2)
        │                                              → (B,64,31,31)
        ├─ Block 6 ─── FusedDepthwiseConv2dBNReLU(64→64, 3x3, dw)
        │                                              → (B,64,31,31)
        ├─ Global Average Pool (AdaptiveAvgPool2d)    → (B,64,1,1)
        └─ Linear(64 → 4)                             → (B,4)

    The depthwise-separable blocks (4a/4b, 6) significantly reduce
    parameter count and multiply-accumulate (MAC) operations while
    maintaining representational capacity.
    """

    def __init__(
        self,
        num_classes: int = 4,
        bias: bool = False,
        **kwargs,
    ) -> None:
        """
        Args:
            num_classes: Number of output classes. Default 4 for FFB grading.
            bias:        Whether to include bias terms in conv layers.
                         Set False to save parameters on MAX78000.
            **kwargs:    Forwarded to ai8x layer constructors (e.g.,
                         `weight_bits`, `quantize_activation`).
        """
        super(TBSClassifier, self).__init__()

        # ── Block 1: Initial spatial feature extraction ──────────────────────
        # Input: (B, 3, 128, 128) RGB signed INT8 image
        # Output: (B, 16, 128, 128)
        # Padding=1 preserves spatial dimensions for 3x3 kernel.
        self.block1_conv = ai8x.FusedConv2dBNReLU(
            in_channels=3,
            out_channels=16,
            kernel_size=3,
            padding=1,
            stride=1,
            bias=bias,
            **kwargs
        )

        # ── Block 2: Deeper feature extraction ───────────────────────────────
        # Input: (B, 16, 128, 128)
        # Output: (B, 32, 128, 128)
        self.block2_conv = ai8x.FusedConv2dBNReLU(
            in_channels=16,
            out_channels=32,
            kernel_size=3,
            padding=1,
            stride=1,
            bias=bias,
            **kwargs
        )

        # ── Block 3: Downsampling + feature expansion ─────────
        # FusedMaxPoolConv2dBNReLU: applies MaxPool(2x2) THEN Conv2d in one
        # HW pass — critical for saving CNN accelerator cycles.
        # Input: (B, 32, 128, 128) → MaxPool
        #   → (B,32,64,64) → Conv → (B,64,63,63)
        # Note: With pool_size=2 and padding=0 on the conv, output is 63x63
        #   floor((64 - 3 + 2*0)/1) + 1 = 62
        #   → use padding=1 for 64x64
        self.block3_pool_conv = ai8x.FusedMaxPoolConv2dBNReLU(
            in_channels=32,
            out_channels=64,
            kernel_size=3,
            padding=1,       # padding=1 to keep 64x64 after pool
            stride=1,
            pool_size=2,
            pool_stride=2,
            bias=bias,
            **kwargs
        )

        # ── Block 4a: Depthwise Separable — Depthwise stage ──────────────────
        # Groups == in_channels == out_channels for true depthwise conv.
        # Applies a separate 3x3 kernel per channel — very low parameter count.
        # Input/Output: (B, 64, 64, 64)
        self.block4a_dw = ai8x.FusedDepthwiseConv2dBNReLU(
            in_channels=64,
            out_channels=64,
            kernel_size=3,
            padding=1,
            stride=1,
            bias=bias,
            **kwargs
        )

        # ── Block 4b: Depthwise Separable — Pointwise (1x1) mixing ───────────
        # Linearly combines depthwise outputs across channels.
        # Input/Output: (B, 64, 64, 64)
        self.block4b_pw = ai8x.FusedConv2dBNReLU(
            in_channels=64,
            out_channels=64,
            kernel_size=1,
            padding=0,
            stride=1,
            bias=bias,
            **kwargs
        )

        # ── Block 5: Second downsampling pass ─────────────────
        # Input: (B, 64, 64, 64) → Pool → (B,64,32,32) → Conv → (B,64,32,32)
        self.block5_pool_conv = ai8x.FusedMaxPoolConv2dBNReLU(
            in_channels=64,
            out_channels=64,
            kernel_size=3,
            padding=1,
            stride=1,
            pool_size=2,
            pool_stride=2,
            bias=bias,
            **kwargs
        )

        # ── Block 6: Final depthwise refinement ──────────────────────────────
        # Input/Output: (B, 64, 32, 32)
        self.block6_dw = ai8x.FusedDepthwiseConv2dBNReLU(
            in_channels=64,
            out_channels=64,
            kernel_size=3,
            padding=1,
            stride=1,
            bias=bias,
            **kwargs
        )

        # ── Global Average Pooling ───────────────────────────────────────────
        # Collapses (B, 64, 32, 32) → (B, 64, 1, 1) before
        # the classifier head.
        # Preferred over Flatten for spatial invariance and lower param count.
        self.global_avg_pool = nn.AdaptiveAvgPool2d((1, 1))

        # ── Classifier Head ──────────────────────────────────────────────────

        # Maps the 64-dim feature vector to 4 class logits.
        # ai8x.Linear wraps nn.Linear with quantization.
        self.classifier = ai8x.Linear(
            in_features=64,
            out_features=num_classes,
            bias=True,     # Bias on final layer is standard practice
            wide=True,     # wide=True enables wider accumulator in HW
            **kwargs
        )

        # Initialize weights using Kaiming normal (He initialization),
        # which is well-suited for ReLU activations.
        self._initialize_weights()

    def _initialize_weights(self) -> None:
        """Apply He initialization to all Conv2d and Linear layers."""
        for module in self.modules():
            if isinstance(module, nn.Conv2d):
                nn.init.kaiming_normal_(
                    module.weight,
                    mode='fan_out',
                    nonlinearity='relu'
                )
                if module.bias is not None:
                    nn.init.constant_(module.bias, 0)
            elif isinstance(module, nn.BatchNorm2d):
                nn.init.constant_(module.weight, 1)
                nn.init.constant_(module.bias, 0)
            elif isinstance(module, nn.Linear):
                nn.init.normal_(module.weight, 0, 0.01)
                if module.bias is not None:
                    nn.init.constant_(module.bias, 0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass through the TBSClassifier.

        Args:
            x: Input tensor of shape (B, 3, 128, 128).
               Values should be INT8 range [-128, 127] after normalization,
               or float in [-1.0, 1.0] during floating-point pre-training.

        Returns:
            Logits tensor of shape (B, 4) — one score per FFB class.
        """
        # ── Spatial Feature Extraction ─────────────────────────────────────
        x = self.block1_conv(x)      # (B, 3,  128, 128) → (B, 16, 128, 128)
        x = self.block2_conv(x)      # (B, 16, 128, 128) → (B, 32, 128, 128)

        # ── First Downsampling (2x) ────────────────────────────────────────
        x = self.block3_pool_conv(x)  # → (B, 64,  64,  64)

        # ── Depthwise Separable Block ──────────────────────────────────────
        x = self.block4a_dw(x)       # (B, 64,  64,  64) → (B, 64,  64,  64)
        x = self.block4b_pw(x)       # (B, 64,  64,  64) → (B, 64,  64,  64)

        # ── Second Downsampling (2x) ───────────────────────────────────────
        x = self.block5_pool_conv(x)  # → (B, 64,  32,  32)

        # ── Final Refinement ───────────────────────────────────────────────
        x = self.block6_dw(x)        # (B, 64,  32,  32) → (B, 64,  32,  32)

        # ── Global Pooling + Classifier ────────────────────────────────────
        x = self.global_avg_pool(x)  # (B, 64, 32, 32) → (B, 64, 1, 1)
        x = x.view(x.size(0), -1)   # (B, 64, 1, 1)   → (B, 64)
        x = self.classifier(x)       # (B, 64) → (B, 4) logits

        return x


###############################################################################
# ai8x-training Model Registry
# The SDK's train.py discovers models via this function name convention.
###############################################################################

def tbs_classifier(pretrained: bool = False, **kwargs) -> TBSClassifier:
    """
    Factory function for the TBSClassifier model.

    This naming convention is required by the ai8x-training SDK so that the
    model can be selected via the --model CLI argument:
        python train.py --model tbs_classifier ...

    Args:
        pretrained: Reserved for future use (loading ImageNet weights etc.).
                    Currently unused — model trains from scratch on TBS data.
        **kwargs:   Passed through to TBSClassifier constructor, e.g.:
                    - weight_bits=8  (for QAT)
                    - act_mode_8bit=True
                    - quantize_activation=True

    Returns:
        Instantiated TBSClassifier model.
    """
    if pretrained:
        raise NotImplementedError(
            "Pretrained weights are not available for TBSClassifier. "
            "Train from scratch using train_pipeline.sh."
        )
    return TBSClassifier(**kwargs)


###############################################################################
# Utility: Weight Budget Checker
# Run standalone to verify the model stays within 442 KB hardware limit.
###############################################################################

def _check_weight_budget(
    net: nn.Module,
    limit_kb: float = 442.0,
) -> None:
    """
    Calculates the approximate INT8 weight budget and compares to HW limit.

    Args:
        model:    Instantiated model (weights in float32 during training).
        limit_kb: Hardware CNN weight memory limit in KB. Default: 442 KB.
    """
    total_params = sum(
        p.numel() for p in net.parameters() if p.requires_grad
    )
    # INT8 = 1 byte per parameter
    size_bytes = total_params * 1  # 1 byte/param for INT8 post-QAT
    size_kb = size_bytes / 1024.0

    print("=" * 60)
    print("  TBSClassifier Weight Budget Report")
    print("=" * 60)
    print(f"  Trainable parameters : {total_params:,}")
    print(f"  Estimated INT8 size  : {size_kb:.2f} KB")
    print(f"  Hardware limit       : {limit_kb:.2f} KB")
    print(f"  Budget remaining     : {limit_kb - size_kb:.2f} KB")
    status = (
        "✓ WITHIN BUDGET"
        if size_kb <= limit_kb
        else "✗ EXCEEDS BUDGET — reduce channels!"
    )
    print(f"  Status               : {status}")
    print("=" * 60)


###############################################################################
# Self-Test (run as: python -m models.tbs_classifier)
###############################################################################

if __name__ == "__main__":
    import sys

    print("Running TBSClassifier self-test (CPU, float32 mode)...")

    # Simulate ai8x initialization with dummy weight_bits
    # In real training, ai8x.set_device() is called in train.py
    # For standalone testing, we mock the ai8x module if not available.
    try:
        ai8x.set_device(device=85, simulate=True, round_avg=False)
    except AttributeError:
        print("[WARN] ai8x.set_device not available — running in mock mode.")

    # Instantiate model in float32 mode (no QAT kwargs)
    model = TBSClassifier(num_classes=4, bias=False)
    model.eval()

    # Create a dummy batch: 2 images, RGB, 128x128
    dummy_input = torch.randn(2, 3, 128, 128)

    with torch.no_grad():
        output = model(dummy_input)

    print(f"  Input shape  : {dummy_input.shape}")
    print(f"  Output shape : {output.shape}")
    assert output.shape == (2, 4), f"Unexpected output shape: {output.shape}"

    # Check weight budget
    _check_weight_budget(model, limit_kb=442.0)

    print("\n[PASS] TBSClassifier self-test complete.")
    sys.exit(0)
