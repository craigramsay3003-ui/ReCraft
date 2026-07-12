"""Triangulated fragment interpretation."""

from typing import Mapping

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import Delaunay

from recraft.styles.base import ArtStyle, Parameter, ParameterValue


class FragmentStyle(ArtStyle):
    """Approximate an image with edge-aware coloured triangles."""

    identifier = "fragment"
    display_name = "Fragment"
    description = "Fracture source structure into sampled polygonal regions."
    parameters = (Parameter("detail", "Fragment detail", 180, 40, 500, 10),)

    def process(self, image: Image.Image, parameters: Mapping[str, ParameterValue] | None = None) -> Image.Image:
        values = self.validate_parameters(parameters)
        rgb = np.asarray(image.convert("RGB"))
        height, width = rgb.shape[:2]
        grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        corners = cv2.goodFeaturesToTrack(grey, int(values["detail"]), 0.015, 5)
        points = [] if corners is None else [tuple(point.ravel()) for point in corners]
        border_steps = max(3, int(np.sqrt(int(values["detail"]))))
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
