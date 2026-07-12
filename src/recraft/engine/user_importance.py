"""Non-destructive source-space user importance editing."""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import cv2
import numpy as np
from PIL import Image, ImageDraw

from recraft.core.image_transform import FitMode, ImageTransformSettings

if TYPE_CHECKING:
    from recraft.engine.analysis_result import ImageAnalysis

MASK_MAXIMUM = 1000


class BrushMode(str, Enum):
    """Available importance-painting operations."""

    ADD = "add"
    REDUCE = "reduce"
    ERASE = "erase"


@dataclass
class UserImportanceState:
    """Editable source-space masks and deterministic combination weights."""

    source_size: tuple[int, int]
    mask_size: tuple[int, int]
    add_mask: np.ndarray
    reduce_mask: np.ndarray
    automatic_strength: float = 1.0
    user_strength: float = 1.0
    background_suppression: float = 0.35
    colour_preview: np.ndarray | None = None
    region_preview: np.ndarray | None = None
    focus_add_prepared: np.ndarray | None = None
    focus_reduce_prepared: np.ndarray | None = None

    @classmethod
    def create(cls, source_size: tuple[int, int]) -> "UserImportanceState":
        """Create responsive blank masks matching source aspect ratio."""
        width, height = source_size
        scale = min(1.0, MASK_MAXIMUM / max(width, height))
        mask_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        shape = (mask_size[1], mask_size[0])
        return cls(source_size, mask_size, np.zeros(shape, np.float32), np.zeros(shape, np.float32))

    def clear(self) -> None:
        """Clear all user edits and pending selections."""
        self.add_mask.fill(0); self.reduce_mask.fill(0)
        self.colour_preview = None; self.region_preview = None
        self.focus_add_prepared = None; self.focus_reduce_prepared = None

    def paint_source(self, x: float, y: float, radius: float, strength: float, mode: BrushMode) -> None:
        """Paint one circular dab using normalized source coordinates."""
        if not 0 <= x <= 1 or not 0 <= y <= 1:
            return
        strength = float(np.clip(strength, 0, 1))
        px, py = x * (self.mask_size[0] - 1), y * (self.mask_size[1] - 1)
        pr = max(1, radius * max(self.mask_size))
        layer = Image.new("L", self.mask_size, 0)
        ImageDraw.Draw(layer).ellipse((px - pr, py - pr, px + pr, py + pr), fill=round(strength * 255))
        dab = np.asarray(layer, dtype=np.float32) / 255.0
        if mode is BrushMode.ADD:
            self.add_mask = np.maximum(self.add_mask, dab); self.reduce_mask *= 1 - dab
        elif mode is BrushMode.REDUCE:
            self.reduce_mask = np.maximum(self.reduce_mask, dab); self.add_mask *= 1 - dab
        else:
            self.add_mask *= 1 - dab; self.reduce_mask *= 1 - dab

    def apply_selection(self, mask: np.ndarray, mode: BrushMode, strength: float = 1.0) -> None:
        """Merge a source-space selection into additive or subtractive masks."""
        resized = cv2.resize(mask.astype(np.float32), self.mask_size, interpolation=cv2.INTER_LINEAR)
        resized = np.clip(resized * strength, 0, 1)
        if mode is BrushMode.ADD:
            self.add_mask = np.maximum(self.add_mask, resized); self.reduce_mask *= 1 - resized
        elif mode is BrushMode.REDUCE:
            self.reduce_mask = np.maximum(self.reduce_mask, resized); self.add_mask *= 1 - resized
        else:
            self.add_mask *= 1 - resized; self.reduce_mask *= 1 - resized


def canvas_to_source(
    point: tuple[float, float],
    source_size: tuple[int, int],
    settings: ImageTransformSettings,
    canvas_size: tuple[int, int],
) -> tuple[float, float] | None:
    """Map a canvas pixel to normalized original-source coordinates."""
    state = settings.validated(); sw, sh = source_size; width, height = canvas_size
    q = state.rotation_quarters % 4
    ww, wh = (sh, sw) if q % 2 else (sw, sh)
    base = min(width / ww, height / wh) if state.fit_mode is FitMode.FIT else max(width / ww, height / wh)
    scale = base * state.zoom; rw, rh = ww * scale, wh * scale
    left = (width - rw) / 2 + state.pan_x * abs(width - rw) / 2
    top = (height - rh) / 2 + state.pan_y * abs(height - rh) / 2
    x, y = (point[0] - left) / scale, (point[1] - top) / scale
    if not 0 <= x < ww or not 0 <= y < wh: return None
    if state.flip_horizontal: x = ww - 1 - x
    if state.flip_vertical: y = wh - 1 - y
    if q == 0: ox, oy = x, y
    elif q == 1: ox, oy = y, sh - 1 - x
    elif q == 2: ox, oy = sw - 1 - x, sh - 1 - y
    else: ox, oy = sw - 1 - y, x
    return float(np.clip(ox / max(sw - 1, 1), 0, 1)), float(np.clip(oy / max(sh - 1, 1), 0, 1))


def render_source_mask(mask: np.ndarray, settings: ImageTransformSettings, output_size: tuple[int, int]) -> np.ndarray:
    """Transform a source-space mask into an aligned prepared-canvas mask."""
    state = settings.validated(); width, height = output_size
    image = Image.fromarray(np.clip(mask * 255, 0, 255).astype(np.uint8), "L")
    if state.rotation_quarters: image = image.rotate(-90 * state.rotation_quarters, expand=True)
    if state.flip_horizontal: image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if state.flip_vertical: image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    base = min(width / image.width, height / image.height) if state.fit_mode is FitMode.FIT else max(width / image.width, height / image.height)
    scale = base * state.zoom
    image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.BILINEAR)
    left = round((width - image.width) / 2 + state.pan_x * abs(width - image.width) / 2)
    top = round((height - image.height) / 2 + state.pan_y * abs(height - image.height) / 2)
    canvas = Image.new("L", output_size, 0); canvas.paste(image, (left, top))
    return np.asarray(canvas, dtype=np.float32) / 255.0


def combine_importance(
    automatic: np.ndarray,
    add: np.ndarray,
    reduce: np.ndarray,
    background: np.ndarray,
    automatic_strength: float = 1.0,
    user_strength: float = 1.0,
    background_suppression: float = 0.35,
) -> np.ndarray:
    """Combine automatic, user, and background evidence into 0..1."""
    result = automatic * automatic_strength + add * user_strength - reduce * user_strength
    result -= background * background_suppression * (1 - add)
    return np.clip(result, 0, 1).astype(np.float32)


def apply_user_importance(
    analysis: "ImageAnalysis",
    state: UserImportanceState | None,
    settings: ImageTransformSettings,
) -> "ImageAnalysis":
    """Attach aligned user masks and deterministic combined importance."""
    if state is None:
        return analysis
    shape = analysis.automatic_importance.shape
    size = (shape[1], shape[0])
    add = render_source_mask(state.add_mask, settings, size)
    reduce = render_source_mask(state.reduce_mask, settings, size)
    if state.focus_add_prepared is not None:
        add = np.maximum(add, cv2.resize(state.focus_add_prepared, size, interpolation=cv2.INTER_LINEAR))
    if state.focus_reduce_prepared is not None:
        reduce = np.maximum(reduce, cv2.resize(state.focus_reduce_prepared, size, interpolation=cv2.INTER_LINEAR))
    combined = combine_importance(
        analysis.automatic_importance, add, reduce, analysis.background_mask,
        state.automatic_strength, state.user_strength, state.background_suppression,
    )
    return analysis.with_user_masks(importance=combined, additive=add, subtractive=reduce)
