"""Colour interpretation helpers."""

import cv2
import numpy as np


def cluster_colours(rgb: np.ndarray, cluster_count: int = 6) -> tuple[np.ndarray, np.ndarray]:
    """K-means cluster RGB pixels and return labels plus display colours."""
    height, width = rgb.shape[:2]
    pixels = rgb.reshape(-1, 3).astype(np.float32)
    count = max(1, min(cluster_count, len(pixels)))
    cv2.setRNGSeed(42)
    _, labels, centres = cv2.kmeans(
        pixels,
        count,
        None,
        (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5),
        3,
        cv2.KMEANS_PP_CENTERS,
    )
    return labels.reshape(height, width).astype(np.int16), np.clip(centres, 0, 255).astype(np.uint8)
