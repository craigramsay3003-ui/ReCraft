"""Safe image loading helpers."""

from pathlib import Path

from PIL import Image, UnidentifiedImageError


class ImageLoadError(ValueError):
    """Raised when a source image cannot be loaded."""


def load_image(path: str | Path) -> Image.Image:
    """Load *path* into an independent RGB Pillow image."""
    source = Path(path)
    if not source.is_file():
        raise ImageLoadError(f"Image file does not exist: {source}")
    try:
        with Image.open(source) as image:
            image.load()
            return image.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageLoadError(f"Unable to read image '{source}': {exc}") from exc
