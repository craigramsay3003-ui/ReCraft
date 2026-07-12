"""Vector-like Contour path extraction and PNG rendering."""

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from recraft.engine.analysis_result import ImageAnalysis


@dataclass(frozen=True)
class ContourPath:
    """One reusable iso-level path."""

    points: tuple[tuple[float, float], ...]
    level: float
    importance: float
    closed: bool

    @property
    def length(self) -> float:
        """Return path length in source pixels."""
        points = np.asarray(self.points, dtype=np.float32)
        return float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())


@dataclass(frozen=True)
class ContourResult:
    """Contour geometry shared by raster and mesh exporters."""

    width: int
    height: int
    paths: tuple[ContourPath, ...]
    raw_paths: tuple[ContourPath, ...]
    source_aspect_ratio: float


@dataclass(frozen=True)
class ContourSettings:
    """Understandable controls translated into path filtering behavior."""

    detail: int = 14
    smoothing: float = 2.0
    subject_emphasis: float = 0.75
    background_reduction: float = 0.65
    line_weight: int = 1
    simplification: float = 1.0
    minimum_spacing: float = 5.0
    invert: bool = False
    major_only: bool = False


def extract_contours(analysis: ImageAnalysis, settings: ContourSettings) -> ContourResult:
    """Extract, simplify, and importance-filter brightness-band paths."""
    grey = analysis.map_at_image_size(analysis.enhanced_greyscale)
    if settings.invert: grey = 1 - grey
    sigma = max(0.1, settings.smoothing)
    smoothed = cv2.GaussianBlur((grey * 255).astype(np.uint8), (0, 0), sigma)
    importance = analysis.map_at_image_size(analysis.importance_map)
    background = analysis.map_at_image_size(analysis.background_mask)
    raw: list[ContourPath] = []; kept: list[ContourPath] = []
    levels = np.linspace(18, 237, max(3, settings.detail))
    min_length = max(10.0, min(analysis.image.size) * 0.018)
    for level_index, level in enumerate(levels):
        binary = (smoothed >= level).astype(np.uint8) * 255
        found, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        for contour in found:
            points = contour[:, 0, :]
            if len(points) < 3: continue
            closed = float(np.linalg.norm(points[0] - points[-1])) <= 2.0
            sampled_importance = float(importance[points[:, 1], points[:, 0]].mean())
            sampled_background = float(background[points[:, 1], points[:, 0]].mean())
            simplified = cv2.approxPolyDP(contour, max(0.1, settings.simplification), closed)[:, 0, :]
            path = ContourPath(tuple((float(x), float(y)) for x, y in simplified), float(level / 255), sampled_importance, closed)
            raw.append(path)
            required = min_length * (1.7 - settings.subject_emphasis * sampled_importance)
            required *= 1 + settings.background_reduction * sampled_background * 2
            if settings.major_only: required *= 2.2
            if path.length < required: continue
            if closed and abs(cv2.contourArea(contour)) < required * 1.5: continue
            if sampled_background > 0.65 and sampled_importance < 0.35 and level_index % 3: continue
            if level_index % max(1, round(settings.minimum_spacing / 3)) and sampled_importance < 0.52: continue
            kept.append(path)
    return ContourResult(analysis.image.width, analysis.image.height, tuple(kept), tuple(raw), analysis.image.width / analysis.image.height)


def render_contours(result: ContourResult, line_width: int = 1, raw: bool = False) -> Image.Image:
    """Render a ContourResult without re-detecting raster lines."""
    canvas = np.full((result.height, result.width, 3), 248, np.uint8)
    for path in result.raw_paths if raw else result.paths:
        points = np.rint(path.points).astype(np.int32).reshape(-1, 1, 2)
        shade = round(35 + path.level * 90)
        cv2.polylines(canvas, [points], path.closed, (shade, shade, shade), max(1, line_width), cv2.LINE_AA)
    return Image.fromarray(canvas, "RGB")


def contour_importance_image(result: ContourResult) -> Image.Image:
    """Render retained paths coloured by their importance."""
    canvas = np.zeros((result.height, result.width, 3), np.uint8)
    for path in result.paths:
        points = np.rint(path.points).astype(np.int32).reshape(-1, 1, 2)
        colour = (round(255 * (1 - path.importance)), round(255 * path.importance), 60)
        cv2.polylines(canvas, [points], path.closed, colour, 1, cv2.LINE_AA)
    return Image.fromarray(canvas, "RGB")
