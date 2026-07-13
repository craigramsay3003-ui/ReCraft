"""Background generation and export for the focused relief workflow."""

from pathlib import Path
from time import perf_counter

from PIL import Image
from PySide6.QtCore import QObject, Signal, Slot

from recraft.core.diagnostics import get_diagnostic_logger
from recraft.relief.heightmap import create_relief_height_map
from recraft.relief.mesh import build_relief_mesh, export_relief_3mf, export_relief_stl
from recraft.relief.presets import ReliefSettings


class ReliefWorker(QObject):
    """Build one immutable preview or full-resolution export off the UI thread."""

    stage_changed = Signal(str, int)
    preview_ready = Signal(object, object, object)
    export_ready = Signal(str, object, object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, prepared: Image.Image, settings: ReliefSettings, operation: str = "preview", path: str | None = None) -> None:
        super().__init__(); self.prepared = prepared.copy(); self.settings = settings.validated(); self.operation = operation; self.path = path

    @Slot()
    def run(self) -> None:
        """Generate a bounded relief and always release the worker thread."""
        logger = get_diagnostic_logger(); timings: dict[str, float] = {}; started = perf_counter()
        try:
            preview = self.operation == "preview"; resolution = self.settings.preview_resolution if preview else self.settings.export_resolution
            self.stage_changed.emit("Analysing broad forms", 20); stage = perf_counter(); height_map = create_relief_height_map(self.prepared, self.settings, resolution); timings["height_map"] = perf_counter() - stage
            self.stage_changed.emit("Building watertight plaque", 65); stage = perf_counter(); mesh = build_relief_mesh(height_map.values, self.settings, preview=preview); timings["mesh"] = perf_counter() - stage
            if preview:
                self.stage_changed.emit("Preparing interactive preview", 90); self.preview_ready.emit(height_map.prepared_image, height_map.values, mesh)
            else:
                if not self.path: raise ValueError("An export path is required")
                self.stage_changed.emit(f"Writing {self.operation.upper()}", 88); stage = perf_counter()
                if self.operation == "stl": export_relief_stl(mesh, self.path)
                elif self.operation == "3mf": export_relief_3mf(mesh, self.path)
                else: raise ValueError(f"Unsupported relief export: {self.operation}")
                timings["export"] = perf_counter() - stage; self.export_ready.emit(str(Path(self.path)), height_map.values, mesh)
            timings["total"] = perf_counter() - started
            logger.info("relief style=%s source=%s height_map=%s preview=%s triangles=%s memory=%.1fMB watertight=%s stages=%s export=%s", self.settings.style.value, self.prepared.size, height_map.values.shape[::-1], preview, mesh.triangle_count, mesh.estimated_memory_mb, mesh.watertight, timings, self.path if not preview else "none")
        except Exception as exc:
            logger.exception("Recoverable relief failure style=%s source=%s operation=%s", self.settings.style.value, self.prepared.size, self.operation)
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self.finished.emit()
