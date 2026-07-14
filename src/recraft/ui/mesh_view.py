"""Interactive software 3D viewer for actual Contour relief geometry."""

import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPolygonF, QWheelEvent
from PySide6.QtWidgets import QWidget

from recraft.core.mesh_camera import MeshCamera, ProjectionMode
from recraft.exporters.contour_mesh import ContourMeshResult, ReliefColours
from recraft.core.diagnostics import get_diagnostic_logger

MAX_RENDER_FACES = 6000


def build_coherent_render_surface(
    result: ContourMeshResult,
    maximum_faces: int = MAX_RENDER_FACES,
) -> tuple[np.ndarray, np.ndarray]:
    """Create a continuous bounded plaque surface from the exported height map.

    Sampling complete rows and columns preserves the full outline and topology.
    It avoids the holes produced by selecting unrelated triangles from the
    export mesh while retaining the same orientation and relative heights.
    """
    field = np.asarray(result.relief_map, np.float64)
    if field.ndim != 2 or min(field.shape) < 2:
        raise ValueError("A two-dimensional relief map is required for preview")
    source_rows, source_columns = field.shape
    # Reserve enough of the face budget for the four side walls and rear.
    top_budget = max(2, maximum_faces - 600)
    scale = min(
        1.0,
        np.sqrt(top_budget / (2 * (source_rows - 1) * (source_columns - 1))),
    )
    columns = max(2, min(source_columns, int((source_columns - 1) * scale) + 1))
    rows = max(2, min(source_rows, int((source_rows - 1) * scale) + 1))
    while 2 * (columns - 1) * (rows - 1) > top_budget:
        if columns >= rows and columns > 2:
            columns -= 1
        elif rows > 2:
            rows -= 1
        else:
            break

    column_indices = np.unique(np.rint(np.linspace(0, source_columns - 1, columns)).astype(np.int64))
    row_indices = np.unique(np.rint(np.linspace(0, source_rows - 1, rows)).astype(np.int64))
    sample = field[np.ix_(row_indices, column_indices)]
    rows, columns = sample.shape
    xs = column_indices / (source_columns - 1) * result.width_mm
    ys = row_indices / (source_rows - 1) * result.height_mm
    xx, yy = np.meshgrid(xs, ys)

    field_min, field_max = float(field.min()), float(field.max())
    relief_min, relief_max = result.ridge_height_range
    if field_max - field_min < 1e-12:
        relief = np.full_like(sample, relief_min)
    else:
        relief = relief_min + (sample - field_min) / (field_max - field_min) * (relief_max - relief_min)
    base_top = float(result.mesh.bounds[1, 2]) - relief_max
    top = np.column_stack((xx.ravel(), yy.ravel(), (base_top + relief).ravel()))

    cell_y, cell_x = np.mgrid[0:rows - 1, 0:columns - 1]
    a = (cell_y * columns + cell_x).ravel()
    b = a + 1
    d = a + columns
    c = d + 1
    top_faces = np.vstack((np.column_stack((a, b, c)), np.column_stack((a, c, d))))

    boundary = (
        list(range(columns))
        + [row * columns + columns - 1 for row in range(1, rows)]
        + list(range((rows - 1) * columns + columns - 2, (rows - 1) * columns - 1, -1))
        + [row * columns for row in range(rows - 2, 0, -1)]
    )
    edge = np.asarray(boundary, np.int64)
    bottom_offset = len(top)
    bottom_edge = np.column_stack((top[edge, 0], top[edge, 1], np.zeros(len(edge))))
    next_edge = np.roll(edge, -1)
    bottom_indices = bottom_offset + np.arange(len(edge), dtype=np.int64)
    next_bottom = np.roll(bottom_indices, -1)
    side_faces = np.vstack(
        (
            np.column_stack((edge, next_bottom, next_edge)),
            np.column_stack((edge, bottom_indices, next_bottom)),
        )
    )
    # The flat rear is intentionally omitted from the software preview. Its two
    # enormous triangles overlap the front in an orbit view and cannot be
    # depth-buffered correctly by QPainter. Export still contains the rear.
    vertices = np.vstack((top, bottom_edge))
    faces = np.vstack((top_faces, side_faces)).astype(np.int64, copy=False)
    if len(faces) > maximum_faces:
        raise ValueError("Coherent preview exceeded its display face budget")
    return vertices, faces


class MeshView(QWidget):
    """Orbitable viewer that never changes or regenerates export geometry."""

    camera_changed = Signal()

    def __init__(self) -> None:
        super().__init__(); self.camera = MeshCamera(); self.result: ContourMeshResult | None = None; self.colours = ReliefColours("#7D848D", "#B9BEC5"); self.wireframe = False; self._last: QPoint | None = None; self._panning = False
        self._vertices = np.empty((0, 3), np.float64); self._faces = np.empty((0, 3), np.int64); self._normals = np.empty((0, 3), np.float64); self._raised = np.empty(0, bool); self._height_tone = np.empty(0, np.float64); self._render_error: str | None = None
        self.setMinimumSize(300, 240); self.setMouseTracking(True); self.setStyleSheet("background:#15181D")

    def set_mesh(self, result: ContourMeshResult | None, colours: ReliefColours | None = None) -> None:
        """Display the exact mesh used by STL/3MF export."""
        self.result = result; self.colours = colours or self.colours; self._render_error = None
        if result is None:
            self._vertices = np.empty((0, 3)); self._faces = np.empty((0, 3), np.int64); self._normals = np.empty((0, 3)); self._raised = np.empty(0, bool); self._height_tone = np.empty(0)
        else:
            # Copy compact immutable render buffers once. Camera movement never
            # reaches into trimesh caches or mutates export geometry.
            self._vertices, self._faces = build_coherent_render_surface(result)
            edges_a = self._vertices[self._faces[:, 1]] - self._vertices[self._faces[:, 0]]; edges_b = self._vertices[self._faces[:, 2]] - self._vertices[self._faces[:, 0]]
            normals = np.cross(edges_a, edges_b); lengths = np.linalg.norm(normals, axis=1, keepdims=True); self._normals = normals / np.maximum(lengths, 1e-12)
            if hasattr(result, "triangle_count"):
                # A bas-relief is one continuous material, not separate ridges.
                # Lighting should communicate its shape without false bands.
                self._raised = np.ones(len(self._faces), bool)
            else:
                threshold = result.mesh.bounds[1, 2] - max(result.ridge_height_range[1] * .65, .05)
                self._raised = self._vertices[self._faces, 2].max(axis=1) > threshold
            face_height = self._vertices[self._faces, 2].mean(axis=1)
            height_span = max(float(face_height.max() - face_height.min()), 1e-12)
            self._height_tone = (face_height - face_height.min()) / height_span
            for array in (self._vertices, self._faces, self._normals, self._raised, self._height_tone): array.flags.writeable = False
        self.update()

    def set_colours(self, colours: ReliefColours) -> None:
        self.colours = colours.validated(); self.update()

    def set_standard_view(self, name: str) -> None:
        self.camera.set_view(name); self.update(); self.camera_changed.emit()

    def reset_camera(self) -> None:
        self.camera.reset(); self.update(); self.camera_changed.emit()

    def fit_mesh(self) -> None:
        self.camera.distance = 2.6; self.camera.pan_x = self.camera.pan_y = 0; self.update(); self.camera_changed.emit()

    def set_projection(self, mode: str) -> None:
        self.camera.projection = ProjectionMode(mode.title()); self.update(); self.camera_changed.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._last = event.position().toPoint(); self._panning = event.button() == Qt.MouseButton.MiddleButton or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._last is None: return
        current = event.position().toPoint(); delta = current - self._last; self._last = current
        if self._panning: self.camera.pan(delta.x() / max(self.width(), 1), -delta.y() / max(self.height(), 1))
        else: self.camera.orbit(delta.x() * .5, -delta.y() * .5)
        self.update(); self.camera_changed.emit()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._last = None

    def wheelEvent(self, event: QWheelEvent) -> None:
        self.camera.zoom(.88 if event.angleDelta().y() > 0 else 1.14); self.update(); self.camera_changed.emit()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self); painter.fillRect(self.rect(), QColor("#15181D")); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#303840"), 1)); painter.drawLine(20, self.height() - 25, self.width() - 20, self.height() - 25)
        if self.result is None or not len(self._faces):
            painter.setPen(QColor("#AEB5BF")); painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Build a relief to inspect the actual mesh"); return
        try:
            points, depth = self.camera.project(self._vertices, (self.width(), self.height()))
            indices = np.argsort(depth[self._faces].mean(axis=1)); base = QColor(self.colours.base); contour = QColor(self.colours.contour)
            for face_index in indices:
                face = self._faces[face_index]; colour = QColor(contour if self._raised[face_index] else base); normal = self._normals[face_index]
                light = abs(float(normal @ np.array([.3, -.4, .86])))
                shade = max(.35, min(1.0, .30 + .25 * light + .45 * self._height_tone[face_index])); colour = colour.darker(round(100 / shade))
                polygon = QPolygonF([QPointF(*points[vertex]) for vertex in face]); painter.setBrush(colour); painter.setPen(QPen(QColor("#111318") if self.wireframe else colour, 1)); painter.drawPolygon(polygon)
        except Exception as exc:  # Qt paint callbacks must never terminate the process
            self._render_error = f"{type(exc).__name__}: {exc}"; get_diagnostic_logger().exception("Recoverable mesh viewer paint failure")
            painter.setPen(QColor("#F28B82")); painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "3D preview could not be drawn. Export geometry remains intact.")
