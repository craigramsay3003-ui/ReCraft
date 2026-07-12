"""Background worker for style previews and full-resolution exports."""

from collections.abc import Mapping
from pathlib import Path

from PIL import Image
import numpy as np
from PySide6.QtCore import QObject, Signal, Slot

from recraft.core.image_transform import ImageTransformSettings
from recraft.core.prepared_image import analyse_prepared_preview, render_style_export, render_style_preview
from recraft.styles.base import ArtStyle, ParameterValue
from recraft.engine.user_importance import UserImportanceState
from recraft.engine.user_importance import render_source_mask
from recraft.styles.contour_geometry import contour_height_image, contour_importance_image, render_contours


class RenderWorker(QObject):
    """Render one immutable preview or export job outside the UI thread."""

    preview_ready = Signal(object)
    export_ready = Signal(str, int, int)
    failed = Signal(str)
    finished = Signal()
    geometry_ready = Signal(object)
    analysis_ready = Signal(object)

    def __init__(
        self,
        source: Image.Image,
        settings: ImageTransformSettings,
        style: ArtStyle,
        parameters: Mapping[str, ParameterValue],
        export_path: str | None = None,
        debug_view: str | None = None,
        user_importance: UserImportanceState | None = None,
    ) -> None:
        super().__init__()
        self._source = source.copy()
        self._settings = settings
        self._style = style
        self._parameters = dict(parameters)
        self._export_path = export_path
        self._debug_view = debug_view
        self._user_importance = user_importance

    @Slot()
    def run(self) -> None:
        """Execute the configured job and always report completion."""
        try:
            if self._export_path is None:
                if self._debug_view:
                    analysis = analyse_prepared_preview(self._source, self._settings, user_importance=self._user_importance)
                    self.analysis_ready.emit(analysis)
                    if self._debug_view in ("Raw Contour Paths", "Filtered Contour Paths", "Contour Importance View", "Contour Height View"):
                        generator = getattr(self._style, "generate", None)
                        if generator is None: raise ValueError("Contour diagnostics require the Contour style")
                        contours = generator(analysis, self._parameters)
                        if self._debug_view == "Raw Contour Paths": result = render_contours(contours, raw=True)
                        elif self._debug_view == "Filtered Contour Paths": result = render_contours(contours)
                        elif self._debug_view == "Contour Importance View": result = contour_importance_image(contours)
                        else: result = contour_height_image(contours)
                    elif self._debug_view in ("Colour Selection Preview", "Region Selection Preview"):
                        source_mask = None
                        if self._user_importance is not None:
                            source_mask = self._user_importance.colour_preview if self._debug_view.startswith("Colour") else self._user_importance.region_preview
                        if source_mask is None:
                            result = Image.new("RGB", analysis.image.size, "black")
                        else:
                            mask = render_source_mask(source_mask, self._settings, analysis.image.size)
                            result = Image.fromarray(np.clip(mask * 255, 0, 255).astype(np.uint8), "L").convert("RGB")
                    else:
                        result = analysis.debug_image(self._debug_view)
                else:
                    if getattr(self._style, "identifier", "") == "contour":
                        analysis = analyse_prepared_preview(self._source, self._settings, user_importance=self._user_importance)
                        self.analysis_ready.emit(analysis)
                        contours = self._style.generate(analysis, self._parameters)
                        self.geometry_ready.emit(contours)
                        result = render_contours(contours, int(self._parameters.get("line_weight", 1)))
                    else:
                        result = render_style_preview(
                            self._source, self._settings, self._style, self._parameters, user_importance=self._user_importance
                        )
                self.preview_ready.emit(result)
            else:
                result = render_style_export(
                    self._source, self._settings, self._style, self._parameters, user_importance=self._user_importance
                )
                result.save(self._export_path, "PNG")
                self.export_ready.emit(
                    str(Path(self._export_path)), result.width, result.height
                )
        except Exception as exc:  # worker boundary must return errors to the UI
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self.finished.emit()
