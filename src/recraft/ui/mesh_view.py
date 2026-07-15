"""Interactive software 3D viewer for actual Contour relief geometry."""

import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen, QPolygonF, QTransform, QWheelEvent
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


def relief_shading_texture(relief_map: np.ndarray) -> QImage:
    """Render full height-map detail as a smooth neutral lighting texture."""
    field = np.flipud(np.asarray(relief_map, np.float32))
    low, high = float(field.min()), float(field.max())
    if high - low < 1e-8:
        normalized = np.zeros_like(field)
    else:
        normalized = np.clip((field - low) / (high - low), 0, 1)
    gradient_y, gradient_x = np.gradient(normalized)
    normal_x = -gradient_x * 3.5
    normal_y = -gradient_y * 3.5
    normal_z = np.ones_like(normal_x)
    length = np.sqrt(normal_x**2 + normal_y**2 + normal_z**2)
    directional = np.clip(
        (normal_x * -.35 + normal_y * -.25 + normal_z * .90) / length,
        0,
        1,
    )
    shade = np.clip(.18 + .42 * normalized + .40 * directional, 0, 1)
    grey = np.asarray(45 + shade * 190, np.uint8)
    rgb = np.ascontiguousarray(np.repeat(grey[..., None], 3, axis=2))
    return QImage(
        rgb.data,
        rgb.shape[1],
        rgb.shape[0],
        rgb.strides[0],
        QImage.Format.Format_RGB888,
    ).copy()


def rgb_surface_texture(pixels: np.ndarray) -> QImage:
    """Copy an aligned RGB colour map into immutable Qt-owned storage."""
    rgb = np.ascontiguousarray(np.asarray(pixels, np.uint8))
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("Surface colour texture must be an RGB array")
    return QImage(
        rgb.data,
        rgb.shape[1],
        rgb.shape[0],
        rgb.strides[0],
        QImage.Format.Format_RGB888,
    ).copy()


def colour_relief_texture(pixels: np.ndarray, relief_map: np.ndarray) -> QImage:
    """Apply restrained matte relief lighting without moving aligned colour."""
    rgb = np.asarray(pixels, np.float32)
    # ReliefMesh stores row zero at physical Y=0 (image bottom), while an image
    # texture stores row zero at its visual top.
    field = np.flipud(np.asarray(relief_map, np.float32))
    if rgb.shape[:2] != field.shape:
        raise ValueError("Colour texture and relief map must have identical dimensions")
    low, high = float(field.min()), float(field.max())
    normalized = np.zeros_like(field) if high - low < 1e-8 else np.clip((field - low) / (high - low), 0, 1)
    gradient_y, gradient_x = np.gradient(normalized)
    normal_x, normal_y, normal_z = -gradient_x * 2.5, -gradient_y * 2.5, np.ones_like(field)
    length = np.sqrt(normal_x**2 + normal_y**2 + normal_z**2)
    directional = np.clip((normal_x * -.30 + normal_y * -.22 + normal_z * .93) / length, 0, 1)
    light = np.clip(.62 + .24 * directional + .14 * normalized, .55, 1.0)
    return rgb_surface_texture(np.clip(rgb * light[..., None], 0, 255).astype(np.uint8))


class MeshView(QWidget):
    """Orbitable viewer that never changes or regenerates export geometry."""

    camera_changed = Signal()

    def __init__(self) -> None:
        super().__init__(); self.camera = MeshCamera(); self.result: ContourMeshResult | None = None; self.colours = ReliefColours("#7D848D", "#B9BEC5"); self.wireframe = False; self._last: QPoint | None = None; self._panning = False
        self._vertices = np.empty((0, 3), np.float64); self._faces = np.empty((0, 3), np.int64); self._normals = np.empty((0, 3), np.float64); self._raised = np.empty(0, bool); self._height_tone = np.empty(0, np.float64); self._relief_texture: QImage | None = None; self._texture_corners = np.empty((0, 3), np.float64); self._render_error: str | None = None
        self.setMinimumSize(300, 240); self.setMouseTracking(True); self.setStyleSheet("background:#15181D")

    def set_mesh(self, result: ContourMeshResult | None, colours: ReliefColours | None = None, surface_pixels: np.ndarray | None = None) -> None:
        """Display the exact mesh used by STL/3MF export."""
        self.result = result; self.colours = colours or self.colours; self._render_error = None
        if result is None:
            self._vertices = np.empty((0, 3)); self._faces = np.empty((0, 3), np.int64); self._normals = np.empty((0, 3)); self._raised = np.empty(0, bool); self._height_tone = np.empty(0); self._relief_texture = None; self._texture_corners = np.empty((0, 3))
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
            self._relief_texture = colour_relief_texture(surface_pixels, result.relief_map) if surface_pixels is not None else relief_shading_texture(result.relief_map)
            field = np.asarray(result.relief_map, np.float64)
            relief_low, relief_high = result.ridge_height_range
            field_low, field_high = float(field.min()), float(field.max())
            if field_high - field_low < 1e-12:
                physical_relief = np.full_like(field, relief_low)
            else:
                physical_relief = relief_low + (field - field_low) / (field_high - field_low) * (relief_high - relief_low)
            base_top = float(result.mesh.bounds[1, 2]) - relief_high
            self._texture_corners = np.array(
                [
                    [0, result.height_mm, base_top + physical_relief[-1, 0]],
                    [result.width_mm, result.height_mm, base_top + physical_relief[-1, -1]],
                    [result.width_mm, 0, base_top + physical_relief[0, -1]],
                    [0, 0, base_top + physical_relief[0, 0]],
                ],
                np.float64,
            )
            for array in (self._vertices, self._faces, self._normals, self._raised, self._height_tone, self._texture_corners): array.flags.writeable = False
        self.update()

    def set_surface_texture(self, pixels: np.ndarray | None) -> None:
        """Change colour representation without touching geometry or camera."""
        if self.result is None:
            return
        self._relief_texture = relief_shading_texture(self.result.relief_map) if pixels is None else colour_relief_texture(pixels, self.result.relief_map)
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
            if self._relief_texture is not None and self.camera.pitch >= 0:
                corners, _ = self.camera.project(self._texture_corners, (self.width(), self.height()))
                source = QPolygonF(
                    [
                        QPointF(0, 0),
                        QPointF(self._relief_texture.width(), 0),
                        QPointF(self._relief_texture.width(), self._relief_texture.height()),
                        QPointF(0, self._relief_texture.height()),
                    ]
                )
                destination = QPolygonF([QPointF(*point) for point in corners])
                transform = QTransform.quadToQuad(source, destination)
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                painter.setTransform(transform)
                painter.drawImage(QPointF(0, 0), self._relief_texture)
                painter.restore()
        except Exception as exc:  # Qt paint callbacks must never terminate the process
            self._render_error = f"{type(exc).__name__}: {exc}"; get_diagnostic_logger().exception("Recoverable mesh viewer paint failure")
            painter.setPen(QColor("#F28B82")); painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "3D preview could not be drawn. Export geometry remains intact.")
