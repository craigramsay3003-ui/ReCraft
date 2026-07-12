"""Background Contour STL generation."""

from PIL import Image
from PySide6.QtCore import QObject, Signal, Slot

from recraft.core.image_transform import ImageTransformSettings
from recraft.core.prepared_image import analyse_prepared_preview
from recraft.engine.user_importance import UserImportanceState
from recraft.exporters.contour_mesh import ContourMeshSettings, export_contour_stl
from recraft.styles.contour import ContourStyle
from recraft.styles.base import ParameterValue


class MeshWorker(QObject):
    """Generate and validate one Contour STL outside the UI thread."""

    exported = Signal(str, float, float, int, int, bool)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, source: Image.Image, transform: ImageTransformSettings, importance: UserImportanceState | None, parameters: dict[str, ParameterValue], mesh_settings: ContourMeshSettings, path: str) -> None:
        super().__init__(); self.source = source.copy(); self.transform = transform; self.importance = importance
        self.parameters = dict(parameters); self.mesh_settings = mesh_settings; self.path = path

    @Slot()
    def run(self) -> None:
        """Generate paths, build a watertight mesh, and save STL."""
        try:
            analysis = analyse_prepared_preview(self.source, self.transform, maximum=1200, user_importance=self.importance)
            contours = ContourStyle().generate(analysis, self.parameters)
            if not contours.paths: raise ValueError("No printable Contour paths remain; increase Detail or Subject Emphasis")
            result = export_contour_stl(contours, self.mesh_settings, self.path)
            self.exported.emit(self.path, result.width_mm, result.height_mm, len(result.mesh.vertices), len(result.mesh.faces), result.watertight)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally: self.finished.emit()
