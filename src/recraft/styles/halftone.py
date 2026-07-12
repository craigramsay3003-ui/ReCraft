"""Circle-based halftone interpretation."""

from typing import Mapping

import cv2
import numpy as np
from PIL import Image, ImageDraw

from recraft.styles.base import ArtStyle, Parameter, ParameterValue
from recraft.engine.analysis_result import ImageAnalysis


class HalftoneStyle(ArtStyle):
    """Represent local darkness with circles on a regular grid."""

    identifier = "halftone"
    display_name = "Halftone"
    description = "Reconstruct the image with brightness-sized circles."
    parameters = (
        Parameter("cell_size", "Cell size", 10, 4, 40),
        Parameter("contrast", "Contrast", 1.3, 0.5, 3.0, 0.1),
    )

    def process(self, analysis: ImageAnalysis, parameters: Mapping[str, ParameterValue] | None = None) -> Image.Image:
        values = self.validate_parameters(parameters)
        grey = analysis.map_at_image_size(analysis.enhanced_greyscale)
        local = cv2.GaussianBlur(grey, (0, 0), 8)
        pixels = np.clip(0.5 + (grey - local) * float(values["contrast"]), 0, 1)
        importance = analysis.map_at_image_size(analysis.importance_map)
        cell = int(values["cell_size"])
        canvas = Image.new("RGB", analysis.image.size, "white")
        draw = ImageDraw.Draw(canvas)
        width, height = analysis.image.size
        fine = max(3, cell // 2)
        for top in range(0, height, fine):
            for left in range(0, width, fine):
                bottom, right = min(top + fine, height), min(left + fine, width)
                detail = float(importance[top:bottom, left:right].mean())
                if detail < 0.42 and (top // fine % 2 or left // fine % 2):
                    continue
                block = pixels[top:bottom, left:right]
                size = fine if detail >= 0.42 else cell
                darkness = 1.0 - float(block.mean())
                minimum = 0.07 + 0.12 * detail
                radius = max(minimum, darkness) * size * 0.46
                cx, cy = left + fine / 2, top + fine / 2
                draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill="black")
        return canvas
