"""Aligned original, palette, and monochrome colour-map generation."""

import cv2
import numpy as np
from PIL import Image, ImageColor

from recraft.core_engine.models import ColourMapData, ColourMode, CoreSettings, MonochromeMaterial


MATERIAL_COLOURS = {
    MonochromeMaterial.MATTE_WHITE: "#E7E4DE",
    MonochromeMaterial.STONE: "#A9A39A",
    MonochromeMaterial.WARM_GREY: "#91877C",
    MonochromeMaterial.BLACK: "#292C30",
}


def _hex(rgb: np.ndarray) -> str:
    return "#" + "".join(f"{int(value):02X}" for value in rgb)


def _merge_small_islands(labels: np.ndarray, minimum_pixels: int) -> np.ndarray:
    """Merge isolated colour islands into the dominant surrounding label."""
    cleaned = labels.astype(np.int32, copy=True)
    kernel = np.ones((3, 3), np.uint8)
    for label in np.unique(cleaned):
        mask = np.asarray(cleaned == label, np.uint8)
        count, components, statistics, _ = cv2.connectedComponentsWithStats(mask, 8)
        for component in range(1, count):
            if statistics[component, cv2.CC_STAT_AREA] >= minimum_pixels:
                continue
            island = components == component
            ring = cv2.dilate(island.astype(np.uint8), kernel, iterations=1).astype(bool) & ~island
            neighbours = cleaned[ring]
            if neighbours.size:
                choices, counts = np.unique(neighbours, return_counts=True)
                cleaned[island] = int(choices[np.argmax(counts)])
    return cleaned


def artistic_palette(
    rgb: np.ndarray,
    palette_size: int,
    minimum_pixels: int,
    locked: tuple[str | None, ...] = (),
) -> tuple[np.ndarray, np.ndarray, tuple[str, ...]]:
    """Reduce RGB pixels into coherent perceptual Lab colour regions."""
    height, width = rgb.shape[:2]
    smoothed = cv2.bilateralFilter(rgb, 9, 35, 35)
    lab = cv2.cvtColor(smoothed, cv2.COLOR_RGB2LAB)
    samples = lab.reshape(-1, 3).astype(np.float32)
    cv2.setRNGSeed(20260715)
    _, labels, centres = cv2.kmeans(
        samples,
        palette_size,
        None,
        (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, .2),
        5,
        cv2.KMEANS_PP_CENTERS,
    )
    centres_u8 = np.clip(centres, 0, 255).astype(np.uint8).reshape(1, -1, 3)
    palette_rgb = cv2.cvtColor(centres_u8, cv2.COLOR_LAB2RGB).reshape(-1, 3)
    for index, value in enumerate(locked):
        if value is not None and index < len(palette_rgb):
            palette_rgb[index] = ImageColor.getrgb(value)
    # Reassignment makes replaced/locked colours real rather than cosmetic.
    palette_lab = cv2.cvtColor(palette_rgb.reshape(1, -1, 3), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    distances = ((samples[:, None, :] - palette_lab[None, :, :]) ** 2).sum(axis=2)
    labels_2d = np.argmin(distances, axis=1).reshape(height, width).astype(np.int32)
    labels_2d = cv2.medianBlur(labels_2d.astype(np.uint8), 5).astype(np.int32)
    labels_2d = _merge_small_islands(labels_2d, minimum_pixels)
    pixels = palette_rgb[labels_2d]
    return pixels.astype(np.uint8), labels_2d, tuple(_hex(colour) for colour in palette_rgb)


def build_colour_map(image: Image.Image, settings: CoreSettings, size: tuple[int, int], minimum_pixels: int) -> ColourMapData:
    """Create the selected stable colour representation at relief resolution."""
    state = settings.validated()
    rgb = np.asarray(image.convert("RGB").resize(size, Image.Resampling.LANCZOS), np.uint8)
    mode = ColourMode(state.colour_mode)
    if mode is ColourMode.ORIGINAL:
        labels = np.zeros(size[::-1], np.int32)
        return ColourMapData(rgb, labels, (), mode, False, ("Original photographic colour is preview-only for filament printing.",))
    if mode is ColourMode.ARTISTIC:
        pixels, labels, palette = artistic_palette(rgb, state.palette_size, minimum_pixels, state.locked_palette)
        return ColourMapData(pixels, labels, palette, mode, state.palette_size <= 4, ())
    material = state.custom_material_colour if state.monochrome_material is MonochromeMaterial.CUSTOM else MATERIAL_COLOURS[MonochromeMaterial(state.monochrome_material)]
    colour = np.asarray(ImageColor.getrgb(material), np.uint8)
    pixels = np.broadcast_to(colour, (*size[::-1], 3)).copy()
    return ColourMapData(pixels, np.zeros(size[::-1], np.int32), (material.upper(),), mode, True, ())
