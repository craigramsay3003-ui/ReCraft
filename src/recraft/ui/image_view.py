"""Image preview widget."""

from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel


class ImageView(QLabel):
    """Display a Pillow image scaled to the available panel."""

    def __init__(self, placeholder: str) -> None:
        super().__init__(placeholder)
        self._image: Image.Image | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(320, 260)
        self.setStyleSheet("QLabel { background: #20242a; color: #aeb5bf; border-radius: 5px; }")

    def set_image(self, image: Image.Image | None) -> None:
        """Set the image presented by this widget."""
        self._image = image.copy() if image else None
        self._refresh()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        if self._image is None:
            return
        pixmap = QPixmap.fromImage(ImageQt(self._image))
        self.setPixmap(pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
