"""Background Contour STL generation."""

from PIL import Image
from PySide6.QtCore import QObject, Signal, Slot
from time import perf_counter

from recraft.core.image_transform import ImageTransformSettings
from recraft.core.prepared_image import analyse_prepared_preview
from recraft.engine.user_importance import UserImportanceState
from recraft.exporters.contour_mesh import ContourMeshSettings, ReliefColours, build_contour_mesh, export_contour_3mf, export_contour_stl, render_relief_preview
from recraft.styles.contour_geometry import ContourResult
from recraft.styles.contour import ContourStyle
from recraft.styles.base import ParameterValue
from recraft.core.diagnostics import PipelineMetrics, get_diagnostic_logger
from recraft.engine.analysis_result import ImageAnalysis
from recraft.engine.user_importance import apply_user_importance


class MeshWorker(QObject):
    """Generate and validate one Contour STL outside the UI thread."""

    exported = Signal(str, float, float, int, int, bool)
    preview_ready = Signal(object)
    geometry_ready = Signal(object)
    mesh_ready = Signal(object)
    failed = Signal(str)
    finished = Signal()
    metrics_ready = Signal(object)

    def __init__(self, source: Image.Image, transform: ImageTransformSettings, importance: UserImportanceState | None, parameters: dict[str, ParameterValue], mesh_settings: ContourMeshSettings, path: str | None, colours: ReliefColours | None = None, export_format: str = "stl", contour_result: ContourResult | None = None, analysis: ImageAnalysis | None = None, preset: str = "Custom") -> None:
        super().__init__(); self.source = source.copy(); self.transform = transform; self.importance = importance
        self.parameters = dict(parameters); self.mesh_settings = mesh_settings; self.path = path; self.colours = colours or ReliefColours(); self.export_format = export_format; self.contour_result = contour_result; self.analysis = analysis; self.preset = preset

    @Slot()
    def run(self) -> None:
        """Generate paths, build a watertight mesh, and save STL."""
        logger = get_diagnostic_logger(); started = perf_counter(); stages: dict[str, float] = {}; contours = self.contour_result
        if contours is not None: stages.update({"analysis_cached": 0.0, "contours_cached": 0.0})
        try:
            if contours is None:
                stage = perf_counter()
                analysis = apply_user_importance(self.analysis, self.importance, self.transform) if self.analysis is not None else analyse_prepared_preview(self.source, self.transform, maximum=1200, user_importance=self.importance)
                stages["analysis"] = perf_counter() - stage; stage = perf_counter()
                contours = ContourStyle().generate(analysis, self.parameters)
                stages["contours"] = perf_counter() - stage
                self.geometry_ready.emit(contours)
            if not contours.paths: raise ValueError("No printable Contour paths remain; increase Detail or Subject Emphasis")
            stage = perf_counter()
            if self.path:
                result = export_contour_3mf(contours, self.mesh_settings, self.colours, self.path) if self.export_format == "3mf" else export_contour_stl(contours, self.mesh_settings, self.path)
                self.exported.emit(self.path, result.width_mm, result.height_mm, len(result.mesh.vertices), len(result.mesh.faces), result.watertight)
            else:
                result = build_contour_mesh(contours, self.mesh_settings)
            stages["mesh_and_export" if self.path else "mesh"] = perf_counter() - stage
            self.mesh_ready.emit(result)
            self.preview_ready.emit(render_relief_preview(result, self.colours))
            metrics = PipelineMetrics(self.preset, self.source.size, (self.transform.output_width, self.transform.output_height), result.retained_path_count, result.sampled_point_count, len(result.mesh.vertices), len(result.mesh.faces), result.estimated_memory_mb, stage_seconds=stages, warnings=result.warnings)
            logger.info(metrics.summary()); self.metrics_ready.emit(metrics)
        except Exception as exc:
            logger.exception("Recoverable mesh failure preset=%s source=%s output=%s elapsed=%.3fs", self.preset, self.source.size, (self.transform.output_width, self.transform.output_height), perf_counter() - started)
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally: self.finished.emit()
