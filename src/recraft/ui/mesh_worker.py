"""Background Contour STL generation."""

from PIL import Image
from PySide6.QtCore import QObject, Signal, Slot

from recraft.core.image_transform import ImageTransformSettings
from recraft.core.prepared_image import analyse_prepared_preview
from recraft.engine.user_importance import UserImportanceState
from recraft.exporters.contour_mesh import ContourMeshSettings, ReliefColours, build_contour_mesh, export_contour_3mf, export_contour_stl, render_relief_preview
from recraft.styles.contour_geometry import ContourResult
from recraft.styles.contour import ContourStyle
from recraft.styles.base import ParameterValue


class MeshWorker(QObject):
    """Generate and validate one Contour STL outside the UI thread."""

    exported = Signal(str, float, float, int, int, bool)
    preview_ready = Signal(object)
    geometry_ready = Signal(object)
    mesh_ready = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, source: Image.Image, transform: ImageTransformSettings, importance: UserImportanceState | None, parameters: dict[str, ParameterValue], mesh_settings: ContourMeshSettings, path: str | None, colours: ReliefColours | None = None, export_format: str = "stl", contour_result: ContourResult | None = None) -> None:
        super().__init__(); self.source = source.copy(); self.transform = transform; self.importance = importance
        self.parameters = dict(parameters); self.mesh_settings = mesh_settings; self.path = path; self.colours = colours or ReliefColours(); self.export_format = export_format; self.contour_result = contour_result

    @Slot()
    def run(self) -> None:
        """Generate paths, build a watertight mesh, and save STL."""
        try:
            contours = self.contour_result
            if contours is None:
                analysis = analyse_prepared_preview(self.source, self.transform, maximum=1200, user_importance=self.importance)
                contours = ContourStyle().generate(analysis, self.parameters)
                self.geometry_ready.emit(contours)
            if not contours.paths: raise ValueError("No printable Contour paths remain; increase Detail or Subject Emphasis")
            if self.path:
                result = export_contour_3mf(contours, self.mesh_settings, self.colours, self.path) if self.export_format == "3mf" else export_contour_stl(contours, self.mesh_settings, self.path)
                self.exported.emit(self.path, result.width_mm, result.height_mm, len(result.mesh.vertices), len(result.mesh.faces), result.watertight)
            else:
                result = build_contour_mesh(contours, self.mesh_settings)
            self.mesh_ready.emit(result)
            self.preview_ready.emit(render_relief_preview(result, self.colours))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally: self.finished.emit()
