"""Typed result object representing reusable Image DNA."""

from dataclasses import dataclass, replace

import numpy as np
import cv2
from PIL import Image

from recraft.engine.importance import apply_user_masks


@dataclass(frozen=True)
class ImageAnalysis:
    """All shared interpretation maps extracted from one prepared image."""

    image: Image.Image
    greyscale: np.ndarray
    enhanced_greyscale: np.ndarray
    edge_map: np.ndarray
    gradient_magnitude: np.ndarray
    colour_labels: np.ndarray
    colour_centres: np.ndarray
    texture_map: np.ndarray
    saliency_map: np.ndarray
    face_rectangles: tuple[tuple[int, int, int, int], ...]
    face_landmarks: tuple[np.ndarray, ...]
    face_mask: np.ndarray
    background_mask: np.ndarray
    subject_mask: np.ndarray
    centre_weight: np.ndarray
    local_contrast: np.ndarray
    automatic_importance: np.ndarray
    importance_mask: np.ndarray | None = None
    additive_brush_mask: np.ndarray | None = None
    subtractive_brush_mask: np.ndarray | None = None

    @property
    def importance_map(self) -> np.ndarray:
        """Return automatic importance combined with optional user layers."""
        return apply_user_masks(
            self.automatic_importance,
            self.importance_mask,
            self.additive_brush_mask,
            self.subtractive_brush_mask,
        )

    def with_user_masks(
        self,
        importance: np.ndarray | None = None,
        additive: np.ndarray | None = None,
        subtractive: np.ndarray | None = None,
    ) -> "ImageAnalysis":
        """Return a copy carrying future non-destructive user mask edits."""
        candidate = replace(
            self,
            importance_mask=importance,
            additive_brush_mask=additive,
            subtractive_brush_mask=subtractive,
        )
        _ = candidate.importance_map
        return candidate

    def map_at_image_size(self, layer: np.ndarray, nearest: bool = False) -> np.ndarray:
        """Resize an analysis map to the full prepared canvas when required."""
        target = self.image.size
        if layer.shape[:2] == (target[1], target[0]):
            return layer
        interpolation = cv2.INTER_NEAREST if nearest else cv2.INTER_LINEAR
        return cv2.resize(layer, target, interpolation=interpolation).astype(layer.dtype)

    def debug_image(self, name: str) -> Image.Image:
        """Render a named analysis layer as an RGB developer preview."""
        maps = {
            "Edge Map": self.edge_map,
            "Importance Map": self.importance_map,
            "Automatic Importance": self.automatic_importance,
            "Combined Importance": self.importance_map,
            "User Add Mask": self.additive_brush_mask if self.additive_brush_mask is not None else np.zeros_like(self.automatic_importance),
            "User Reduce Mask": self.subtractive_brush_mask if self.subtractive_brush_mask is not None else np.zeros_like(self.automatic_importance),
            "Background Suppression": self.background_mask,
            "Face Mask": self.face_mask,
            "Background Mask": self.background_mask,
            "Saliency": self.saliency_map,
            "Texture": self.texture_map,
            "Subject Mask": self.subject_mask,
        }
        if name == "Colour Clusters":
            rgb = self.colour_centres[self.colour_labels]
            return Image.fromarray(rgb.astype(np.uint8), "RGB")
        try:
            layer = maps[name]
        except KeyError as exc:
            raise KeyError(f"Unknown analysis view: {name}") from exc
        grey = np.clip(layer * 255, 0, 255).astype(np.uint8)
        return Image.fromarray(grey, "L").convert("RGB")
