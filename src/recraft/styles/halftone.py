"""Circle-based halftone interpretation."""

from typing import Mapping

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance

from recraft.styles.base import ArtStyle, Parameter, ParameterValue


class HalftoneStyle(ArtStyle):
    """Represent local darkness with circles on a regular grid."""

    identifier = "halftone"
    display_name = "Halftone"
    description = "Reconstruct the image with brightness-sized circles."
    parameters = (
        Parameter("cell_size", "Cell size", 10, 4, 40),
        Parameter("contrast", "Contrast", 1.3, 0.5, 3.0, 0.1),
    )

    def process(self, image: Image.Image, parameters: Mapping[str, ParameterValue] | None = None) -> Image.Image:
        values = self.validate_parameters(parameters)
        source = ImageEnhance.Contrast(image.convert("L")).enhance(float(values["contrast"]))
        pixels = np.asarray(source)
        cell = int(values["cell_size"])
        canvas = Image.new("RGB", image.size, "white")
        draw = ImageDraw.Draw(canvas)
        width, height = image.size
        for top in range(0, height, cell):
            for left in range(0, width, cell):
                block = pixels[top:min(top + cell, height), left:min(left + cell, width)]
                radius = (1.0 - float(block.mean()) / 255.0) * cell * 0.48
                if radius >= 0.3:
                    cx, cy = left + cell / 2, top + cell / 2
                    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill="black")
        return canvas
