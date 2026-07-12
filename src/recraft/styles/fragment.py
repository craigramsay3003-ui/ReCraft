"""Triangulated fragment interpretation."""

from typing import Mapping

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import Delaunay

from recraft.styles.base import ArtStyle, Parameter, ParameterValue
from recraft.engine.analysis_result import ImageAnalysis


class FragmentStyle(ArtStyle):
    """Approximate an image with edge-aware coloured triangles."""

    identifier = "fragment"
    display_name = "Fragment"
    description = "Fracture source structure into sampled polygonal regions."
    parameters = (Parameter("detail", "Fragment detail", 180, 40, 500, 10),)

    def process(self, analysis: ImageAnalysis, parameters: Mapping[str, ParameterValue] | None = None) -> Image.Image:
        values = self.validate_parameters(parameters)
        rgb = np.asarray(analysis.image)
        height, width = rgb.shape[:2]
        detail = int(values["detail"])
        importance = analysis.map_at_image_size(analysis.importance_map)
        enhanced = analysis.map_at_image_size(analysis.enhanced_greyscale)
        corners = cv2.goodFeaturesToTrack((enhanced * 255).astype(np.uint8), detail, 0.012, 4)
        points = [] if corners is None else [tuple(point.ravel()) for point in corners]
        grid_step = max(8, int(np.sqrt(width * height / max(detail, 1))))
        points.extend((x, y) for y in range(0, height, grid_step) for x in range(0, width, grid_step))
        rng = np.random.default_rng(42)
        candidates = rng.integers((0, 0), (width, height), size=(detail * 3, 2))
        for x, y in candidates:
            if rng.random() < 0.12 + 0.88 * float(importance[y, x]):
                points.append((x, y))
        border_steps = max(3, int(np.sqrt(detail)))
        points.extend((x, y) for x in np.linspace(0, width - 1, border_steps) for y in (0, height - 1))
        points.extend((x, y) for y in np.linspace(0, height - 1, border_steps) for x in (0, width - 1))
        unique = np.unique(np.rint(points).astype(int), axis=0)
        triangulation = Delaunay(unique)
        result = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(result)
        for simplex in triangulation.simplices:
            polygon = unique[simplex]
            center = np.clip(np.rint(polygon.mean(axis=0)).astype(int), (0, 0), (width - 1, height - 1))
            colour = tuple(int(channel) for channel in rgb[center[1], center[0]])
            draw.polygon([tuple(point) for point in polygon], fill=colour, outline=tuple(max(0, c - 25) for c in colour))
        return result
