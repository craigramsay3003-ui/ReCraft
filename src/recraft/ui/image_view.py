"""Image preview widget with optional zoom and pan gestures."""

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPixmap, QWheelEvent
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
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(280, 240)
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
        if self._image is None:
            return
        pixmap = QPixmap.fromImage(ImageQt(self._image))
        self.setPixmap(
            pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _image_point(self, x: float, y: float) -> tuple[float, float] | None:
        """Map widget coordinates into the displayed image pixel space."""
        if self._image is None: return None
        scale = min(self.width() / self._image.width, self.height() / self._image.height)
        shown_w, shown_h = self._image.width * scale, self._image.height * scale
        left, top = (self.width() - shown_w) / 2, (self.height() - shown_h) / 2
        if not left <= x < left + shown_w or not top <= y < top + shown_h: return None
        return (x - left) / scale, (y - top) / scale
