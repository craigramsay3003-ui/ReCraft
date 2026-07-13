"""Deterministic positive bas-relief height-map generation."""

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from recraft.engine import analyse_image
from recraft.relief.presets import RELIEF_PRESETS, ReliefSettings


@dataclass(frozen=True)
class ReliefHeightMap:
    """Normalized positive-relief field and its prepared reference image."""

    values: np.ndarray
    prepared_image: Image.Image


def suppress_isolated_spikes(values: np.ndarray, sigma: float = .55) -> np.ndarray:
    """Spread single-pixel height jumps into printable local transitions."""
    return cv2.GaussianBlur(np.asarray(values, np.float32), (0, 0), sigma)


def compose_relief_values(
    luminance: np.ndarray,
    gradient: np.ndarray,
    local_contrast: np.ndarray,
    subject: np.ndarray,
    background: np.ndarray,
    face: np.ndarray,
    settings: ReliefSettings,
) -> np.ndarray:
    """Combine broad tone and restrained structural emphasis into 0..1 height."""
    state = settings.validated(); preset = RELIEF_PRESETS[state.style]
    tone = cv2.GaussianBlur(luminance.astype(np.float32), (0, 0), preset.smoothing)
    values = preset.tonal_weight * tone + preset.edge_weight * gradient + preset.contrast_weight * local_contrast
    focus = np.maximum(subject, face); values += preset.subject_weight * state.subject_emphasis * (.65 * focus + .35 * face)
    values *= 1 - np.clip(background * preset.background_suppression * state.background_strength, 0, .9)
    low, high = np.percentile(values, (2, 98))
    if high - low < 1e-5: result = np.zeros_like(values, np.float32)
    else: result = np.clip((values - low) / (high - low), 0, 1).astype(np.float32)
    result = np.clip(result, 0, 1) ** (1 / state.relief_contrast)
    if preset.height_levels > 1:
        result = np.round(result * (preset.height_levels - 1)) / (preset.height_levels - 1)
        result = cv2.morphologyEx(result, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    if state.invert: result = 1 - result
    return np.clip(result, 0, 1).astype(np.float32)


def create_relief_height_map(image: Image.Image, settings: ReliefSettings, resolution: int) -> ReliefHeightMap:
    """Analyse a resized copy and create a smooth printable height field."""
    state = settings.validated()
    scale = resolution / max(image.size); width = max(32, round(image.width * scale)); height = max(32, round(image.height * scale))
    prepared = image.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
    analysis = analyse_image(prepared)
    values = compose_relief_values(analysis.enhanced_greyscale, analysis.gradient_magnitude, analysis.local_contrast, analysis.subject_mask, analysis.background_mask, analysis.face_mask, state)
    mm_per_pixel = state.physical_width_mm / max(width - 1, 1); kernel = min(5, max(1, round(state.minimum_feature_mm / mm_per_pixel)))
    if kernel > 1:
        shape = np.ones((kernel, kernel), np.uint8); values = cv2.morphologyEx(values, cv2.MORPH_OPEN, shape)
    values = suppress_isolated_spikes(values)
    values = np.clip(values, 0, 1).astype(np.float32); values.flags.writeable = False
    return ReliefHeightMap(values, prepared)
