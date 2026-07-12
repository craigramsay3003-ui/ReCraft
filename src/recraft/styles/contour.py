"""Importance-aware vector-like Contour artwork."""

from typing import Mapping

from PIL import Image

from recraft.engine.analysis_result import ImageAnalysis
from recraft.styles.base import ArtStyle, Parameter, ParameterValue
from recraft.styles.contour_geometry import ContourResult, ContourSettings, extract_contours, render_contours


class ContourStyle(ArtStyle):
    """Generate deliberate brightness-band paths using combined importance."""

    identifier = "contour"
    display_name = "Contour"
    description = "Build clean, importance-aware brightness-band line artwork."
    parameters = (
        Parameter("detail", "Detail", 14, 4, 30),
        Parameter("smoothing", "Smoothing", 2.0, 0.5, 6.0, 0.25),
        Parameter("subject_emphasis", "Subject emphasis", 0.75, 0.0, 1.0, 0.05),
        Parameter("background_reduction", "Background reduction", 0.65, 0.0, 1.0, 0.05),
        Parameter("line_weight", "Line weight", 1, 1, 5),
        Parameter("simplification", "Simplification", 1.0, 0.1, 5.0, 0.1),
        Parameter("major_only", "Major contours only", 0, 0, 1),
        Parameter("invert", "Invert", 0, 0, 1),
    )

    def generate(self, analysis: ImageAnalysis, parameters: Mapping[str, ParameterValue] | None = None) -> ContourResult:
        """Generate reusable Contour paths from Image DNA."""
        values = self.validate_parameters(parameters)
        settings = ContourSettings(
            detail=int(values["detail"]), smoothing=float(values["smoothing"]),
            subject_emphasis=float(values["subject_emphasis"]), background_reduction=float(values["background_reduction"]),
            line_weight=int(values["line_weight"]), simplification=float(values["simplification"]),
            major_only=bool(values["major_only"]), invert=bool(values["invert"]),
        )
        return extract_contours(analysis, settings)

    def process(self, analysis: ImageAnalysis, parameters: Mapping[str, ParameterValue] | None = None) -> Image.Image:
        values = self.validate_parameters(parameters)
        return render_contours(self.generate(analysis, values), int(values["line_weight"]))
