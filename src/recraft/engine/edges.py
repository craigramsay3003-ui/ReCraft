"""Reusable edge, gradient, contrast, and texture analysis."""

import cv2
import numpy as np


def edge_features(greyscale: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return edge, gradient-magnitude, and local-contrast maps in 0..1."""
    grey = np.clip(greyscale * 255, 0, 255).astype(np.uint8)
    blurred = cv2.GaussianBlur(grey, (5, 5), 0)
    gx = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    gradient = cv2.magnitude(gx, gy)
    gradient /= max(float(gradient.max()), 1.0)
    edges = cv2.Canny(blurred, 50, 140).astype(np.float32) / 255.0
    local_mean = cv2.GaussianBlur(greyscale.astype(np.float32), (0, 0), 4)
    contrast = np.abs(greyscale - local_mean)
    contrast /= max(float(contrast.max()), 1e-6)
    return edges, gradient.astype(np.float32), contrast.astype(np.float32)


def texture_map(greyscale: np.ndarray) -> np.ndarray:
    """Estimate local texture using neighbourhood standard deviation."""
    source = greyscale.astype(np.float32)
    mean = cv2.boxFilter(source, -1, (9, 9), normalize=True)
    squared_mean = cv2.boxFilter(source * source, -1, (9, 9), normalize=True)
    texture = np.sqrt(np.maximum(squared_mean - mean * mean, 0))
    return (texture / max(float(texture.max()), 1e-6)).astype(np.float32)
