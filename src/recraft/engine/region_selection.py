"""Connected visual-region selection independent of the UI."""

import cv2
import numpy as np


def select_connected_region(rgb: np.ndarray, point: tuple[int, int], tolerance: float = 20.0, feather: float = 3.0) -> np.ndarray:
    """Grow a connected Lab-colour region from the clicked pixel."""
    height, width = rgb.shape[:2]; x, y = point
    if not 0 <= x < width or not 0 <= y < height: raise ValueError("Selection point is outside the image")
    lab = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)
    distance = np.linalg.norm(lab - lab[y, x], axis=2)
    binary = (distance <= tolerance).astype(np.uint8)
    _, labels = cv2.connectedComponents(binary)
    region = (labels == labels[y, x]).astype(np.float32)
    if feather > 0: region = cv2.GaussianBlur(region, (0, 0), feather)
    return np.clip(region, 0, 1).astype(np.float32)
