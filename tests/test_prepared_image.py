from typing import Mapping

from PIL import Image

from recraft.core.image_transform import ImageTransformSettings
from recraft.core.prepared_image import render_style_export, render_style_preview
from recraft.styles.base import ArtStyle, ParameterValue


class RecordingStyle(ArtStyle):
    """Test style that records the canvas supplied by the pipeline."""

    identifier = "recording"
    display_name = "Recording"
    description = "Records its input size."
    parameters = ()

    def __init__(self) -> None:
        self.received_sizes: list[tuple[int, int]] = []

    def process(
        self,
        image: Image.Image,
        parameters: Mapping[str, ParameterValue] | None = None,
    ) -> Image.Image:
        self.received_sizes.append(image.size)
        return image.copy()


def test_style_processing_receives_prepared_image() -> None:
    style = RecordingStyle()
    source = Image.new("RGB", (400, 300), "red")
    settings = ImageTransformSettings(output_width=1600, output_height=900)
    result = render_style_preview(source, settings, style, maximum=400)
    assert style.received_sizes == [(400, 225)]
    assert result.size == (400, 225)


def test_export_uses_full_resolution_not_preview_resolution() -> None:
    style = RecordingStyle()
    source = Image.new("RGB", (400, 300), "blue")
    settings = ImageTransformSettings(output_width=1200, output_height=800)
    preview = render_style_preview(source, settings, style, maximum=300)
    exported = render_style_export(source, settings, style)
    assert preview.size == (300, 200)
    assert exported.size == (1200, 800)
    assert style.received_sizes == [(300, 200), (1200, 800)]
