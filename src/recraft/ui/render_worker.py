"""Background worker for style previews and full-resolution exports."""

from collections.abc import Mapping
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, Signal, Slot

from recraft.core.image_transform import ImageTransformSettings
from recraft.core.prepared_image import analyse_prepared_preview, render_style_export, render_style_preview
from recraft.styles.base import ArtStyle, ParameterValue


class RenderWorker(QObject):
    """Render one immutable preview or export job outside the UI thread."""

    preview_ready = Signal(object)
    export_ready = Signal(str, int, int)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        source: Image.Image,
        settings: ImageTransformSettings,
        style: ArtStyle,
        parameters: Mapping[str, ParameterValue],
        export_path: str | None = None,
        debug_view: str | None = None,
    ) -> None:
        super().__init__()
        self._source = source.copy()
        self._settings = settings
        self._style = style
        self._parameters = dict(parameters)
        self._export_path = export_path
        self._debug_view = debug_view

    @Slot()
    def run(self) -> None:
        """Execute the configured job and always report completion."""
        try:
            if self._export_path is None:
                if self._debug_view:
                    analysis = analyse_prepared_preview(self._source, self._settings)
                    result = analysis.debug_image(self._debug_view)
                else:
                    result = render_style_preview(
                        self._source, self._settings, self._style, self._parameters
                    )
                self.preview_ready.emit(result)
            else:
                result = render_style_export(
                    self._source, self._settings, self._style, self._parameters
                )
                result.save(self._export_path, "PNG")
                self.export_ready.emit(
                    str(Path(self._export_path)), result.width, result.height
                )
        except Exception as exc:  # worker boundary must return errors to the UI
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self.finished.emit()
