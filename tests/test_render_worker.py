from pathlib import Path
from typing import Mapping

from PIL import Image

from recraft.core.image_transform import ImageTransformSettings
from recraft.styles.base import ArtStyle, ParameterValue
from recraft.ui.render_worker import RenderWorker
from recraft.engine.analysis_result import ImageAnalysis


class CopyStyle(ArtStyle):
    identifier = "copy"
    display_name = "Copy"
    description = "Copies its input for worker tests."
    parameters = ()

    def process(
        self,
        analysis: ImageAnalysis,
        parameters: Mapping[str, ParameterValue] | None = None,
    ) -> Image.Image:
        return analysis.image.copy()


def test_preview_worker_reports_rendered_image() -> None:
    results: list[Image.Image] = []
    errors: list[str] = []
    worker = RenderWorker(
        Image.new("RGB", (40, 20), "red"),
        ImageTransformSettings(output_width=200, output_height=100),
        CopyStyle(),
        {},
    )
    worker.preview_ready.connect(results.append)
    worker.failed.connect(errors.append)
    worker.run()
    assert not errors
    assert len(results) == 1
    assert results[0].size == (200, 100)


def test_export_worker_writes_full_resolution_png(tmp_path: Path) -> None:
    destination = tmp_path / "worker-output.png"
    saved: list[tuple[str, int, int]] = []
    worker = RenderWorker(
        Image.new("RGB", (40, 20), "blue"),
        ImageTransformSettings(output_width=320, output_height=180),
        CopyStyle(),
        {},
        str(destination),
    )
    worker.export_ready.connect(lambda path, width, height: saved.append((path, width, height)))
    worker.run()
    assert saved == [(str(destination), 320, 180)]
    with Image.open(destination) as result:
        assert result.size == (320, 180)
