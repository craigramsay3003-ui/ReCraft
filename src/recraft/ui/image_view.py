"""Image preview widget with optional zoom and pan gestures."""

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import QLabel


class ImageView(QLabel):
    """Display a Pillow image and emit normalized preparation gestures."""

    zoom_requested = Signal(float)
    pan_requested = Signal(float, float)
    image_painted = Signal(float, float)
    image_clicked = Signal(float, float)

    def __init__(self, placeholder: str, interactive: bool = False) -> None:
        super().__init__(placeholder)
        self._image: Image.Image | None = None
        self._interactive = interactive
        self._drag_position: QPoint | None = None
        self._interaction_mode = "pan"
        self._view_zoom = 1.0
        self._view_offset = QPointF(0, 0)
        self._navigation_enabled = False
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(220, 180)
        self.setStyleSheet(
            "QLabel { background: #20242a; color: #aeb5bf; "
            "border: 2px solid #596270; border-radius: 5px; }"
        )
        if interactive:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.setToolTip("Mouse wheel: zoom. Drag: reposition inside the crop frame.")

    def set_interaction_mode(self, mode: str) -> None:
        """Switch between pan, paint, and point-selection gestures."""
        if mode not in ("pan", "paint", "select"): raise ValueError("Unknown image interaction mode")
        self._interaction_mode = mode
        self.setCursor(Qt.CursorShape.CrossCursor if mode != "pan" else Qt.CursorShape.OpenHandCursor)

    def enable_view_navigation(self, enabled: bool = True) -> None:
        """Use wheel/drag for display navigation rather than image preparation."""
        self._navigation_enabled = enabled

    def fit_to_view(self) -> None:
        """Fit the entire image and centre it."""
        self._view_zoom = 1.0; self._view_offset = QPointF(0, 0); self.update()

    def actual_size(self) -> None:
        """Display one image pixel per screen pixel."""
        if self._image is None: return
        fit = min(self.width() / self._image.width, self.height() / self._image.height)
        self._view_zoom = 1 / max(fit, 1e-6); self._view_offset = QPointF(0, 0); self.update()

    def reset_view(self) -> None:
        """Reset display-only zoom and pan."""
        self.fit_to_view()

    def map_widget_to_image(self, x: float, y: float) -> tuple[float, float] | None:
        """Map a widget position through display zoom/pan to image pixels."""
        return self._image_point(x, y)

    def set_image(self, image: Image.Image | None) -> None:
        """Set the image presented by this widget."""
        self._image = image.copy() if image else None
        if image is None:
            self.clear()
            self.setText("Preview unavailable")
        self._refresh()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._refresh()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._interactive and self._image is not None:
            if self._navigation_enabled:
                self._view_zoom = max(.2, min(20, self._view_zoom * (1.12 if event.angleDelta().y() > 0 else .89))); self.update(); event.accept(); return
            self.zoom_requested.emit(0.1 if event.angleDelta().y() > 0 else -0.1)
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._interactive and event.button() == Qt.MouseButton.LeftButton:
            point = self._image_point(event.position().x(), event.position().y())
            if point is not None and self._interaction_mode == "select":
                self.image_clicked.emit(*point); event.accept(); return
            if point is not None and self._interaction_mode == "paint":
                self._drag_position = event.position().toPoint(); self.image_painted.emit(*point); event.accept(); return
            self._drag_position = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_position is not None:
            current = event.position().toPoint()
            if self._interaction_mode == "paint":
                point = self._image_point(event.position().x(), event.position().y())
                if point is not None: self.image_painted.emit(*point)
                self._drag_position = current; event.accept(); return
            delta = current - self._drag_position
            self._drag_position = current
            if self._navigation_enabled:
                self._view_offset += QPointF(delta); self.update(); event.accept(); return
            self.pan_requested.emit(delta.x() / max(1, self.width()), delta.y() / max(1, self.height()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_position is not None:
            self._drag_position = None
            self.setCursor(Qt.CursorShape.CrossCursor if self._interaction_mode != "pan" else Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _refresh(self) -> None:
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._image is None:
            super().paintEvent(event); return
        painter = QPainter(self); painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        pixmap = QPixmap.fromImage(ImageQt(self._image)); scale = self._display_scale()
        width, height = self._image.width * scale, self._image.height * scale
        left = (self.width() - width) / 2 + self._view_offset.x(); top = (self.height() - height) / 2 + self._view_offset.y()
        painter.drawPixmap(QRectF(left, top, width, height), pixmap, QRectF(pixmap.rect()))

    def _display_scale(self) -> float:
        if self._image is None: return 1
        return min(self.width() / self._image.width, self.height() / self._image.height) * self._view_zoom

    def _image_point(self, x: float, y: float) -> tuple[float, float] | None:
        """Map widget coordinates into the displayed image pixel space."""
        if self._image is None: return None
        scale = self._display_scale()
        shown_w, shown_h = self._image.width * scale, self._image.height * scale
        left, top = (self.width() - shown_w) / 2 + self._view_offset.x(), (self.height() - shown_h) / 2 + self._view_offset.y()
        if not left <= x < left + shown_w or not top <= y < top + shown_h: return None
        return (x - left) / scale, (y - top) / scale
