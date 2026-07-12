"""Non-destructive image preparation and composition."""

from dataclasses import dataclass, replace
from enum import Enum

from PIL import Image

MAX_OUTPUT_DIMENSION = 8000
MIN_ZOOM = 1.0
MAX_ZOOM = 10.0


class FitMode(str, Enum):
    """Control how an image is scaled into its output viewport."""

    FIT = "fit"
    FILL = "fill"


ASPECT_RATIO_PRESETS: dict[str, tuple[int, int] | None] = {
    "Original": None,
    "Square 1:1": (1, 1),
    "Portrait 4:5": (4, 5),
    "Portrait 2:3": (2, 3),
    "Landscape 3:2": (3, 2),
    "Landscape 16:9": (16, 9),
}


@dataclass(frozen=True)
class ImageTransformSettings:
    """Describe a non-destructive image composition.

    Pan values are normalized to the range -1 to 1. Rotation is expressed in
    clockwise quarter turns, allowing the UI to avoid cumulative resampling.
    """

    pan_x: float = 0.0
    pan_y: float = 0.0
    zoom: float = 1.0
    rotation_quarters: int = 0
    flip_horizontal: bool = False
    flip_vertical: bool = False
    aspect_ratio: tuple[int, int] | None = None
    output_width: int = 1200
    output_height: int = 1200
    fit_mode: FitMode = FitMode.FILL
    lock_aspect_ratio: bool = True

    def validated(self) -> "ImageTransformSettings":
        """Return a normalized copy or raise a useful validation error."""
        if isinstance(self.output_width, bool) or not isinstance(self.output_width, int):
            raise ValueError("Output width must be a positive integer")
        if isinstance(self.output_height, bool) or not isinstance(self.output_height, int):
            raise ValueError("Output height must be a positive integer")
        if not 1 <= self.output_width <= MAX_OUTPUT_DIMENSION:
            raise ValueError(f"Output width must be between 1 and {MAX_OUTPUT_DIMENSION}")
        if not 1 <= self.output_height <= MAX_OUTPUT_DIMENSION:
            raise ValueError(f"Output height must be between 1 and {MAX_OUTPUT_DIMENSION}")
        if not MIN_ZOOM <= self.zoom <= MAX_ZOOM:
            raise ValueError(f"Zoom must be between {MIN_ZOOM} and {MAX_ZOOM}")
        if not -1.0 <= self.pan_x <= 1.0 or not -1.0 <= self.pan_y <= 1.0:
            raise ValueError("Pan values must be between -1 and 1")
        if self.aspect_ratio is not None:
            if len(self.aspect_ratio) != 2 or any(value <= 0 for value in self.aspect_ratio):
                raise ValueError("Aspect ratio values must be positive")
        try:
            mode = FitMode(self.fit_mode)
        except ValueError as exc:
            raise ValueError("Fit mode must be 'fit' or 'fill'") from exc
        return replace(self, rotation_quarters=self.rotation_quarters % 4, fit_mode=mode)

    def reset(self, source_size: tuple[int, int] | None = None) -> "ImageTransformSettings":
        """Return centred default settings, optionally matching a source ratio."""
        width, height = source_size or (1200, 1200)
        scale = min(1.0, MAX_OUTPUT_DIMENSION / max(width, height))
        width, height = max(1, round(width * scale)), max(1, round(height * scale))
        return ImageTransformSettings(
            aspect_ratio=None,
            output_width=width,
            output_height=height,
            fit_mode=FitMode.FILL,
        )


def size_for_aspect_ratio(
    current_size: tuple[int, int], ratio: tuple[int, int] | None
) -> tuple[int, int]:
    """Return a size with *ratio*, keeping the current width stable."""
    width, height = current_size
    if ratio is None:
        return width, height
    ratio_width, ratio_height = ratio
    return width, max(1, round(width * ratio_height / ratio_width))


def prepare_image(
    source_image: Image.Image,
    settings: ImageTransformSettings,
    output_size: tuple[int, int] | None = None,
) -> Image.Image:
    """Render *source_image* into a new prepared RGB canvas.

    The source object is never mutated. ``output_size`` permits a small preview
    render while retaining exactly the same aspect ratio and composition.
    """
    if source_image.width < 1 or source_image.height < 1:
        raise ValueError("Source image must not be empty")
    state = settings.validated()
    target = output_size or (state.output_width, state.output_height)
    width, height = target
    if any(isinstance(value, bool) or not isinstance(value, int) for value in target):
        raise ValueError("Output dimensions must be positive integers")
    if not 1 <= width <= MAX_OUTPUT_DIMENSION or not 1 <= height <= MAX_OUTPUT_DIMENSION:
        raise ValueError(f"Output dimensions must be between 1 and {MAX_OUTPUT_DIMENSION}")

    working = source_image.convert("RGB")
    if state.rotation_quarters:
        working = working.rotate(-90 * state.rotation_quarters, expand=True)
    if state.flip_horizontal:
        working = working.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if state.flip_vertical:
        working = working.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

    scale_x, scale_y = width / working.width, height / working.height
    base_scale = min(scale_x, scale_y) if state.fit_mode is FitMode.FIT else max(scale_x, scale_y)
    scale = base_scale * state.zoom
    resized_size = (max(1, round(working.width * scale)), max(1, round(working.height * scale)))
    working = working.resize(resized_size, Image.Resampling.LANCZOS)

    travel_x = abs(width - working.width) / 2
    travel_y = abs(height - working.height) / 2
    left = round((width - working.width) / 2 + state.pan_x * travel_x)
    top = round((height - working.height) / 2 + state.pan_y * travel_y)
    canvas = Image.new("RGB", (width, height), "white")
    canvas.paste(working, (left, top))
    return canvas
