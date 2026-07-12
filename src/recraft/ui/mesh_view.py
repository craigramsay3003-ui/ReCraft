"""Interactive software 3D viewer for actual Contour relief geometry."""

import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPolygonF, QWheelEvent
from PySide6.QtWidgets import QWidget

from recraft.core.mesh_camera import MeshCamera, ProjectionMode
from recraft.exporters.contour_mesh import ContourMeshResult, ReliefColours


class MeshView(QWidget):
    """Orbitable viewer that never changes or regenerates export geometry."""

    camera_changed = Signal()

    def __init__(self) -> None:
        super().__init__(); self.camera = MeshCamera(); self.result: ContourMeshResult | None = None; self.colours = ReliefColours(); self.wireframe = False; self._last: QPoint | None = None; self._panning = False
        self.setMinimumSize(420, 320); self.setMouseTracking(True); self.setStyleSheet("background:#15181D")

    def set_mesh(self, result: ContourMeshResult | None, colours: ReliefColours | None = None) -> None:
        """Display the exact mesh used by STL/3MF export."""
        self.result = result; self.colours = colours or self.colours; self.update()

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
        if self.result is None:
            painter.setPen(QColor("#AEB5BF")); painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Build a relief to inspect the actual mesh"); return
        mesh = self.result.mesh; points, depth = self.camera.project(mesh.vertices, (self.width(), self.height()))
        faces = mesh.faces; stride = max(1, len(faces) // 18000); indices = np.arange(0, len(faces), stride); indices = indices[np.argsort(depth[faces[indices]].mean(axis=1))]
        base = QColor(self.colours.base); contour = QColor(self.colours.contour); threshold = self.result.mesh.bounds[1, 2] - max(self.result.ridge_height_range[1] * .65, .05)
        for face_index in indices:
            face = faces[face_index]; raised = float(mesh.vertices[face, 2].max()) > threshold; colour = QColor(contour if raised else base); normal = mesh.face_normals[face_index]; shade = max(.35, min(1.0, .5 + .5 * abs(float(normal @ np.array([.3, -.4, .86]))))); colour = colour.darker(round(100 / shade))
            polygon = QPolygonF([QPointF(*points[vertex]) for vertex in face]); painter.setBrush(colour); painter.setPen(QPen(QColor("#111318") if self.wireframe else colour, 1)); painter.drawPolygon(polygon)
