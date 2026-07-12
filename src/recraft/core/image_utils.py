"""Shared image conversion helpers."""

import numpy as np
from PIL import Image


def rgb_array(image: Image.Image) -> np.ndarray:
    """Return an image as an RGB uint8 NumPy array."""
    return np.asarray(image.convert("RGB"), dtype=np.uint8)


def fit_within(image: Image.Image, max_size: int = 1400) -> Image.Image:
    """Copy and shrink an image while preserving its aspect ratio."""
    result = image.copy()
    result.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    return result
