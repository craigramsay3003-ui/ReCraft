"""Topographic contour interpretation."""

from typing import Mapping

import cv2
import numpy as np
from PIL import Image

from recraft.styles.base import ArtStyle, Parameter, ParameterValue


class ContourStyle(ArtStyle):
    """Draw isolines at evenly spaced brightness levels."""

    identifier = "contour"
    display_name = "Contour"
    description = "Rebuild brightness as layered topographic lines."
    parameters = (Parameter("density", "Contour density", 12, 3, 30),)

    def process(self, image: Image.Image, parameters: Mapping[str, ParameterValue] | None = None) -> Image.Image:
        values = self.validate_parameters(parameters)
        grey = np.asarray(image.convert("L"), dtype=np.uint8)
        canvas = np.full((*grey.shape, 3), 248, dtype=np.uint8)
        for level in np.linspace(10, 245, int(values["density"]), dtype=np.uint8):
            mask = np.where(grey >= level, 255, 0).astype(np.uint8)
            contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            shade = int(35 + 100 * (int(level) / 255))
            cv2.drawContours(canvas, contours, -1, (shade, shade, shade), 1, cv2.LINE_AA)
        return Image.fromarray(canvas, "RGB")
