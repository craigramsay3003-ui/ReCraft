"""General-purpose saliency and subject/background segmentation."""

import cv2
import numpy as np


def saliency_map(greyscale: np.ndarray) -> np.ndarray:
    """Compute spectral-residual saliency without model downloads."""
    small = cv2.resize(greyscale.astype(np.float32), (64, 64), interpolation=cv2.INTER_AREA)
    spectrum = np.fft.fft2(small)
    log_amplitude = np.log(np.abs(spectrum) + 1e-8)
    residual = log_amplitude - cv2.blur(log_amplitude, (3, 3))
    reconstructed = np.fft.ifft2(np.exp(residual + 1j * np.angle(spectrum)))
    saliency = np.abs(reconstructed) ** 2
    saliency = cv2.GaussianBlur(saliency.astype(np.float32), (5, 5), 0)
    saliency = cv2.resize(saliency, (greyscale.shape[1], greyscale.shape[0]), interpolation=cv2.INTER_CUBIC)
    low, high = np.percentile(saliency, (5, 99))
    return np.clip((saliency - low) / max(float(high - low), 1e-6), 0, 1).astype(np.float32)


def centre_weight(shape: tuple[int, int]) -> np.ndarray:
    """Return a soft elliptical centre-prior map in 0..1."""
    height, width = shape
    y, x = np.mgrid[-1:1:complex(height), -1:1:complex(width)]
    distance = np.sqrt(x * x + y * y)
    return np.clip(1.0 - distance / np.sqrt(2), 0, 1).astype(np.float32)


def segment_subject(saliency: np.ndarray, centre: np.ndarray, edges: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Create generic soft subject and background masks from visual evidence."""
    evidence = np.clip(0.62 * saliency + 0.23 * centre + 0.15 * cv2.GaussianBlur(edges, (0, 0), 3), 0, 1)
    threshold = max(0.28, float(np.percentile(evidence, 62)))
    binary = (evidence >= threshold).astype(np.uint8)
    kernel = np.ones((5, 5), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    subject = cv2.GaussianBlur(binary.astype(np.float32), (0, 0), 3)
    subject = np.clip(subject, 0, 1)
    return subject, (1.0 - subject).astype(np.float32)
