"""Automatic and user-adjustable importance-map composition."""

import cv2
import numpy as np


def build_importance(
    edges: np.ndarray,
    gradient: np.ndarray,
    saliency: np.ndarray,
    face_mask: np.ndarray,
    local_contrast: np.ndarray,
    subject_mask: np.ndarray,
    centre: np.ndarray,
) -> np.ndarray:
    """Combine reusable evidence into a normalized preservation priority."""
    boundaries = cv2.GaussianBlur(edges, (0, 0), 1.5)
    combined = (
        0.16 * gradient
        + 0.18 * saliency
        + 0.18 * face_mask
        + 0.14 * local_contrast
        + 0.14 * boundaries
        + 0.12 * subject_mask
        + 0.08 * centre
    )
    low, high = np.percentile(combined, (2, 98))
    return np.clip((combined - low) / max(float(high - low), 1e-6), 0, 1).astype(np.float32)


def apply_user_masks(
    automatic: np.ndarray,
    importance_mask: np.ndarray | None = None,
    additive_brush: np.ndarray | None = None,
    subtractive_brush: np.ndarray | None = None,
) -> np.ndarray:
    """Combine automatic importance with future user-authored mask layers."""
    result = automatic.astype(np.float32).copy()
    for name, mask in (("importance", importance_mask), ("additive", additive_brush), ("subtractive", subtractive_brush)):
        if mask is not None and mask.shape != automatic.shape:
            raise ValueError(f"User {name} mask must match the analysis dimensions")
    if importance_mask is not None:
        result = np.maximum(result, np.clip(importance_mask, 0, 1))
    if additive_brush is not None:
        result += np.clip(additive_brush, 0, 1)
    if subtractive_brush is not None:
        result -= np.clip(subtractive_brush, 0, 1)
    return np.clip(result, 0, 1).astype(np.float32)
