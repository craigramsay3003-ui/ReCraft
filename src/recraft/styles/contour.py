"""Topographic contour interpretation."""

from typing import Mapping

import cv2
import numpy as np
from PIL import Image

from recraft.styles.base import ArtStyle, Parameter, ParameterValue
from recraft.engine.analysis_result import ImageAnalysis


class ContourStyle(ArtStyle):
    """Draw isolines at evenly spaced brightness levels."""

    identifier = "contour"
    display_name = "Contour"
    description = "Rebuild brightness as layered topographic lines."
    parameters = (Parameter("density", "Contour density", 12, 3, 30),)

    def process(self, analysis: ImageAnalysis, parameters: Mapping[str, ParameterValue] | None = None) -> Image.Image:
        values = self.validate_parameters(parameters)
        grey_map = analysis.map_at_image_size(analysis.enhanced_greyscale)
        grey = cv2.GaussianBlur((grey_map * 255).astype(np.uint8), (7, 7), 0)
        importance = analysis.map_at_image_size(analysis.importance_map)
        canvas = np.full((*grey.shape, 3), 248, dtype=np.uint8)
        density = int(values["density"])
        for index, level in enumerate(np.linspace(15, 240, density, dtype=np.uint8)):
            mask = np.where(grey >= level, 255, 0).astype(np.uint8)
            contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            shade = int(35 + 100 * (int(level) / 255))
            kept = []
            for contour in contours:
                if cv2.arcLength(contour, True) < 12 or abs(cv2.contourArea(contour)) < 8:
                    continue
                points = contour[:, 0, :]
                mean_importance = float(importance[points[:, 1], points[:, 0]].mean())
                if mean_importance >= 0.12 or index % 2 == 0:
                    kept.append(cv2.approxPolyDP(contour, 0.7, True))
            cv2.drawContours(canvas, kept, -1, (shade, shade, shade), 1, cv2.LINE_AA)
        edges = analysis.map_at_image_size(analysis.edge_map)
        detail_edges = np.where((edges > 0.3) & (importance > 0.55), 40, 0).astype(np.uint8)
        canvas[detail_edges > 0] = (40, 40, 40)
        return Image.fromarray(canvas, "RGB")
