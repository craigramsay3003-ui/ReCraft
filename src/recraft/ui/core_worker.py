"""Background worker for the ReCraft core and reliable exports."""

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QObject, Signal, Slot

from recraft.core.diagnostics import get_diagnostic_logger
from recraft.core_engine import CoreSettings, render_core
from recraft.core_engine.export import export_core_3mf, export_core_stl


class CoreWorker(QObject):
    """Run the complete core without blocking or discarding a valid preview."""

    stage_changed = Signal(str, int)
    preview_ready = Signal(object)
    export_ready = Signal(str, object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, image: Image.Image, settings: CoreSettings, operation: str = "preview", path: str | None = None) -> None:
        super().__init__()
        self.image = image.copy()
        self.settings = settings.validated()
        self.operation = operation
        self.path = path

    @Slot()
    def run(self) -> None:
        """Generate one preview/export and report recoverable failures."""
        logger = get_diagnostic_logger()
        try:
            preview = self.operation == "preview"
            result = render_core(
                self.image,
                self.settings,
                preview=preview,
                stage_callback=self.stage_changed.emit,
            )
            if preview:
                self.preview_ready.emit(result)
            else:
                if not self.path:
                    raise ValueError("An export path is required")
                self.stage_changed.emit(f"Writing {self.operation.upper()}", 94)
                if self.operation == "stl":
                    export_core_stl(result.mesh, self.path)
                elif self.operation == "3mf":
                    export_core_3mf(result.mesh, self.path)
                else:
                    raise ValueError(f"Unsupported export: {self.operation}")
                self.export_ready.emit(str(Path(self.path)), result)
            logger.info(
                "core subject=%s background=%s detail=%s colour=%s source=%s field=%s preview=%s triangles=%s watertight=%s stages=%s",
                self.settings.subject_emphasis.value,
                self.settings.background.value,
                self.settings.detail.value,
                self.settings.colour_mode.value,
                self.image.size,
                result.relief.values.shape[::-1],
                preview,
                result.mesh.result.triangle_count,
                result.mesh.result.watertight,
                result.stage_seconds,
            )
        except Exception as exc:
            logger.exception("Recoverable ReCraft core failure operation=%s", self.operation)
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self.finished.emit()
