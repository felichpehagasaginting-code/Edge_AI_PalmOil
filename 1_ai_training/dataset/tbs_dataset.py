"""Custom PyTorch Dataset for TBS (Tandan Buah Segar) image classification."""
###############################################################################
# FILE: dataset/tbs_dataset.py
# PROJECT: Edge AI Palm Oil FFB (TBS) Grading System
# DESCRIPTION:
#   Custom PyTorch Dataset class for TBS (Tandan Buah Segar) images.
#   Handles dataset loading, preprocessing, and augmentation for training
#   the TBSClassifier CNN model targeting the MAX78000 hardware.
#
# DATASET DIRECTORY STRUCTURE EXPECTED:
#   dataset/
#   ├── train/
#   │   ├── 0_mentah/        ← Class 0: Unripe bunches
#   │   ├── 1_matang/        ← Class 1: Ripe bunches
#   │   ├── 2_overripe/      ← Class 2: Over-ripe bunches
#   │   └── 3_janjang_kosong/ ← Class 3: Empty bunch
#   └── val/
#       ├── 0_mentah/
#       ├── 1_matang/
#       ├── 2_overripe/
#       └── 3_janjang_kosong/
#
# NORMALIZATION:
#   Images are normalized to the range used by the MAX78000 CNN:
#   Input pixel values are mapped from [0, 255] uint8 → [-128, 127] int8
#   via: pixel_int8 = uint8_pixel - 128
#   In float terms: value = (uint8/255.0 - 0.5) * 2.0  (approx.)
#
# USAGE:
#   train_ds = TBSDataset(root='./data', split='train')
#   val_ds   = TBSDataset(root='./data', split='val')
###############################################################################

import logging
import tempfile
from collections import Counter
from pathlib import Path
from typing import Optional, Tuple, Dict, List

import torch
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from PIL import Image
import numpy as np

# ── Logger Setup ────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)


###############################################################################
# Class Definitions
###############################################################################

# Canonical class index mapping — must match the ai8xize synthesis config
# and the firmware cnn_inference.c grade label array.
CLASS_NAMES: Dict[int, str] = {
    0: "Mentah",          # Unripe
    1: "Matang",          # Ripe (optimal harvest)
    2: "Overripe",        # Over-ripe
    3: "Janjang Kosong"   # Empty bunch
}

NUM_CLASSES: int = len(CLASS_NAMES)

# Target input resolution for MAX78000 CNN
INPUT_SIZE: int = 128  # 128x128 pixels


###############################################################################
# Augmentation Pipelines
###############################################################################

def build_train_transforms() -> transforms.Compose:
    """
    Returns the augmentation pipeline for the TRAINING split.

    Augmentation strategy for industrial conveyor-belt conditions:
      - Random horizontal/vertical flip: simulates random bunch orientation
      - Random rotation (±20°): mimics non-uniform placement on belt
      - ColorJitter: simulates varying LED ring light intensity/color temp
      - RandomPerspective: handles slight camera angle variation
      - Normalize to [-1.0, 1.0]: matches MAX78000 INT8 input expectation
    """
    return transforms.Compose([
        # Step 1: Resize to target resolution
        transforms.Resize(
            (INPUT_SIZE, INPUT_SIZE),
            interpolation=transforms.InterpolationMode.BILINEAR
        ),

        # Step 2: Geometric augmentations
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.RandomVerticalFlip(p=0.3),
        transforms.RandomRotation(degrees=20),
        transforms.RandomPerspective(distortion_scale=0.2, p=0.4),

        # Step 3: Color augmentations (simulate LED ring light variation)
        transforms.ColorJitter(
            brightness=0.3,  # ±30% brightness for lighting fluctuation
            contrast=0.3,    # ±30% contrast
            saturation=0.2,  # ±20% saturation (ripeness color shift)
            hue=0.05   # Slight hue shift for different lighting temps
        ),

        # Step 4: Convert to tensor [0.0, 1.0] float32
        transforms.ToTensor(),

        # Step 5: Normalize to [-1.0, 1.0]
        # This approximates the INT8 range [-128, 127] / 128.0
        # Mean=0.5, Std=0.5 maps [0,1] → [-1, 1]
        transforms.Normalize(
            mean=[0.5, 0.5, 0.5],
            std=[0.5, 0.5, 0.5]
        ),
    ])


def build_val_transforms() -> transforms.Compose:
    """
    Returns the deterministic preprocessing pipeline for the VALIDATION split.
    No augmentation — only resize and normalize.
    """
    return transforms.Compose([
        transforms.Resize(
            (INPUT_SIZE, INPUT_SIZE),
            interpolation=transforms.InterpolationMode.BILINEAR
        ),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.5, 0.5, 0.5],
            std=[0.5, 0.5, 0.5]
        ),
    ])


###############################################################################
# Dataset Class
###############################################################################

class TBSDataset(Dataset):
    """
    PyTorch Dataset for TBS (Tandan Buah Segar) image classification.

    Scans subdirectory names as class labels. The subdirectory naming
    convention must follow: `{class_index}_{class_name}/` to allow
    automatic integer label parsing.

    Example valid directory names:
        0_mentah/
        1_matang/
        2_overripe/
        3_janjang_kosong/

    Args:
        root:      Path to the root dataset directory containing
                   'train/' and 'val/' subdirectories.
        split:     Dataset split — 'train' or 'val'.
        transform: Optional torchvision transform pipeline. If None,
                   the appropriate default pipeline is applied automatically.
    """

    def __init__(
        self,
        root: str,
        split: str = 'train',
        transform: Optional[transforms.Compose] = None
    ) -> None:
        if split not in ('train', 'val'):
            raise ValueError(
                f"Invalid split '{split}'. Must be 'train' or 'val'."
            )

        self.root = Path(root)
        self.split = split
        self.split_dir = self.root / split

        if not self.split_dir.exists():
            raise FileNotFoundError(
                f"Dataset split directory not found: {self.split_dir}\n"
                f"Expected structure: "
                f"{root}/{split}/{{class_index}}_{{class_name}}/"
            )

        # Resolve transform
        self.transform = transform or (
            build_train_transforms() if split == 'train'
            else build_val_transforms()
        )

        # Discover samples
        self.samples: List[Tuple[Path, int]] = []
        self._discover_samples()

        logger.info(
            "[TBSDataset] Split='%s' | Samples=%d | Classes=%d",
            split, len(self.samples), NUM_CLASSES
        )

    def _discover_samples(self) -> None:
        """
        Walks the split directory and builds the (image_path, class_label)
        list.

        Class label is parsed from the leading integer in the directory name:
            '0_mentah' → label = 0
            '1_matang' → label = 1
        """
        class_dirs = sorted([
            d for d in self.split_dir.iterdir()
            if d.is_dir() and not d.name.startswith('.')
        ])

        if not class_dirs:
            raise RuntimeError(
                f"No class subdirectories found in: {self.split_dir}"
            )

        valid_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}

        for class_dir in class_dirs:
            # Parse class index from directory name prefix
            # (e.g., "0_mentah" → 0)
            dir_name = class_dir.name
            try:
                class_idx = int(dir_name.split('_')[0])
            except (ValueError, IndexError):
                logger.warning(
                    "[TBSDataset] Skipping directory '%s' — "
                    "cannot parse class index from name prefix.",
                    dir_name
                )
                continue

            if class_idx not in CLASS_NAMES:
                logger.warning(
                    "[TBSDataset] Skipping directory '%s' — "
                    "class index %d not in CLASS_NAMES.",
                    dir_name, class_idx
                )
                continue

            image_files = [
                f for f in class_dir.iterdir()
                if f.suffix.lower() in valid_extensions
            ]

            if not image_files:
                logger.warning(
                    "[TBSDataset] No images found in class dir: %s",
                    class_dir
                )
                continue

            for img_path in sorted(image_files):
                self.samples.append((img_path, class_idx))

        if not self.samples:
            raise RuntimeError(
                f"[TBSDataset] Zero samples found in {self.split_dir}. "
                f"Check your dataset structure."
            )

    def __len__(self) -> int:
        """Returns total number of samples in this split."""
        return len(self.samples)

    def __getitem__(self, index: int) -> Tuple[torch.Tensor, int]:
        """
        Returns the (image_tensor, class_label) pair for a given index.

        Args:
            index: Sample index in [0, len(self)-1].

        Returns:
            Tuple of:
              - image: Float32 tensor of shape (3, 128, 128), range [-1.0, 1.0]
              - label: Integer class index in {0, 1, 2, 3}
        """
        img_path, class_label = self.samples[index]

        # Load image in RGB mode — discard alpha if present (RGBA/PNG)
        try:
            image = Image.open(img_path).convert('RGB')
        except (IOError, OSError) as exc:
            logger.error(
                "[TBSDataset] Failed to open image: %s — %s",
                img_path, exc
            )
            # Return a zero tensor as fallback to avoid training crash
            dummy = torch.zeros(3, INPUT_SIZE, INPUT_SIZE, dtype=torch.float32)
            return dummy, class_label

        # Apply transform pipeline
        image_tensor = self.transform(image)

        return image_tensor, class_label

    def get_class_weights(self) -> torch.Tensor:
        """
        Computes inverse frequency class weights for handling class imbalance.

        Returns:
            FloatTensor of shape (NUM_CLASSES,) for use with
            nn.CrossEntropyLoss(weight=...).
        """
        label_counts = Counter(label for _, label in self.samples)
        total = len(self.samples)

        weights = torch.zeros(NUM_CLASSES, dtype=torch.float32)
        for cls_idx in range(NUM_CLASSES):
            count = label_counts.get(cls_idx, 1)  # avoid division by zero
            weights[cls_idx] = total / (NUM_CLASSES * count)

        logger.info("[TBSDataset] Class weights: %s", weights.tolist())
        return weights

    def __repr__(self) -> str:
        return (
            f"TBSDataset("
            f"split='{self.split}', "
            f"num_samples={len(self.samples)}, "
            f"num_classes={NUM_CLASSES})"
        )


###############################################################################
# DataLoader Factory
###############################################################################

def build_dataloaders(
    data_root: str,
    batch_size: int = 32,
    num_workers: int = 4,
    pin_memory: bool = True
) -> Tuple[DataLoader, DataLoader]:
    """
    Constructs train and validation DataLoaders for TBS classification.

    Args:
        data_root:   Root directory containing 'train/' and 'val/' subdirs.
        batch_size:  Mini-batch size. 32 is a good default for RTX GPUs.
        num_workers: Number of parallel data loading workers.
        pin_memory:  Whether to use pinned memory for faster GPU transfer.

    Returns:
        Tuple of (train_loader, val_loader).
    """
    train_dataset = TBSDataset(root=data_root, split='train')
    val_dataset = TBSDataset(root=data_root, split='val')

    train_loader = DataLoader(
        dataset=train_dataset,
        batch_size=batch_size,
        shuffle=True,  # Shuffle training data each epoch
        num_workers=num_workers,
        pin_memory=pin_memory,
        drop_last=True,  # Drop incomplete last batch for stable BN stats
        persistent_workers=(num_workers > 0)
    )

    val_loader = DataLoader(
        dataset=val_dataset,
        batch_size=batch_size,
        shuffle=False,  # No shuffle for reproducible validation
        num_workers=num_workers,
        pin_memory=pin_memory,
        drop_last=False
    )

    logger.info(
        "[DataLoader] Train: %d samples, %d batches | "
        "Val: %d samples, %d batches",
        len(train_dataset), len(train_loader),
        len(val_dataset), len(val_loader)
    )

    return train_loader, val_loader


###############################################################################
# Self-Test
###############################################################################

def main() -> None:
    """Quick sanity-check with temporary dummy data structure."""
    # Run: python -m dataset.tbs_dataset

    print("Running TBSDataset self-test with temporary dummy data...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Create dummy class directories and placeholder images
        for split in ('train', 'val'):
            for cls_idx, cls_name in CLASS_NAMES.items():
                cls_folder_name = (
                    f"{cls_idx}_{cls_name.replace(' ', '_').lower()}"
                )
                class_dir = tmp_path / split / cls_folder_name
                class_dir.mkdir(parents=True, exist_ok=True)

                # Create 5 dummy RGB PNG images per class
                for img_idx in range(5):
                    dummy_array = np.random.randint(
                        0, 255, (160, 160, 3), dtype=np.uint8
                    )
                    dummy_img = Image.fromarray(dummy_array)
                    dummy_img.save(class_dir / f"sample_{img_idx:03d}.png")

        # Test Dataset
        ds_train = TBSDataset(root=tmp_dir, split='train')
        ds_val = TBSDataset(root=tmp_dir, split='val')

        print(f"  Train dataset: {repr(ds_train)}")
        print(f"  Val   dataset: {repr(ds_val)}")

        # Test __getitem__
        img_tensor, label = ds_train[0]
        print(f"  Sample tensor shape : {img_tensor.shape}")
        print("  Sample tensor range : "
              f"[{img_tensor.min():.3f}, {img_tensor.max():.3f}]")
        print(f"  Sample label        : {label} ({CLASS_NAMES[label]})")

        assert img_tensor.shape == (3, INPUT_SIZE, INPUT_SIZE), \
            f"Unexpected tensor shape: {img_tensor.shape}"
        assert label in CLASS_NAMES, f"Invalid label: {label}"

        # Test class weights
        weights = ds_train.get_class_weights()
        print(f"  Class weights       : {weights.tolist()}")

        # Test DataLoader
        train_dl, _val_dl = build_dataloaders(
            data_root=tmp_dir,
            batch_size=4,
            num_workers=0  # 0 for safe temp dir access in main process
        )

        for batch_imgs, batch_labels in train_dl:
            print(f"  Batch shape: {batch_imgs.shape}, "
                  f"Labels: {batch_labels.tolist()}")
            break

        print("\n[PASS] TBSDataset self-test complete.")


if __name__ == "__main__":
    main()
