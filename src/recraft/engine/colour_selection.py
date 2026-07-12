"""Perceptual colour selection independent of the UI."""

import cv2
import numpy as np


def select_similar_colour(
    rgb: np.ndarray,
    point: tuple[int, int],
    tolerance: float = 18.0,
    feather: float = 4.0,
    connected_only: bool = False,
) -> np.ndarray:
    """Select Lab-similar pixels, optionally retaining the clicked component."""
    height, width = rgb.shape[:2]; x, y = point
    if not 0 <= x < width or not 0 <= y < height: raise ValueError("Selection point is outside the image")
    lab = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    distance = np.linalg.norm(lab - lab[y, x], axis=2)
    mask = np.clip((tolerance + feather - distance) / max(feather, 1e-6), 0, 1).astype(np.float32)
    if connected_only:
        binary = (mask > 0).astype(np.uint8)
        _, labels = cv2.connectedComponents(binary)
        mask *= labels == labels[y, x]
    return mask
