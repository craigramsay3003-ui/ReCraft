"""Honest analysis-derived focus suggestions and keyword intent mapping."""

from dataclasses import dataclass, field
from enum import Enum

import cv2
import numpy as np

from recraft.engine.analysis_result import ImageAnalysis


class FocusAction(str, Enum):
    """Ways a candidate feature can influence combined importance."""

    AUTO = "automatic"
    ADD = "add focus"
    REDUCE = "reduce focus"
    IGNORE = "ignore"


@dataclass
class FocusFeature:
    """An editable candidate region, never a semantic certainty."""

    identifier: str
    label: str
    explanation: str
    mask: np.ndarray
    action: FocusAction = FocusAction.AUTO


@dataclass
class FocusIntent:
    """Transparent keyword-to-existing-feature interpretation."""

    add_types: set[str] = field(default_factory=set)
    reduce_types: set[str] = field(default_factory=set)
    background_amount: float | None = None
    explanation: str = "No supported focus keywords were found."


def suggest_focus_features(analysis: ImageAnalysis) -> list[FocusFeature]:
    """Generate general visual candidates from existing maps."""
    features: list[FocusFeature] = []
    subject = analysis.subject_mask
    if float(subject.max()) > .1:
        features.append(FocusFeature("likely-subject", "Likely subject", "Central salient region suggested by the subject mask.", subject.copy()))
    for index, (x, y, width, height) in enumerate(analysis.face_rectangles):
        mask = np.zeros_like(subject); mask[y:y + height, x:x + width] = 1; mask = cv2.GaussianBlur(mask, (0, 0), 2)
        features.append(FocusFeature(f"possible-face-{index}", "Possible face", "Optional face-detector candidate; verify visually.", mask))
    bright = np.clip((analysis.greyscale - .72) / .28, 0, 1).astype(np.float32)
    if float(bright.mean()) > .015: features.append(FocusFeature("bright-areas", "Bright areas", "Potential highlights or lights that may distract.", bright))
    repeated = np.clip(analysis.texture_map * analysis.background_mask, 0, 1)
    if float(repeated.mean()) > .02: features.append(FocusFeature("background-pattern", "Prominent background feature", "Repeated texture or high-frequency background candidate.", repeated))
    silhouette = cv2.GaussianBlur(analysis.edge_map * analysis.subject_mask, (0, 0), 1)
    features.append(FocusFeature("subject-silhouette", "Suggested silhouette", "Boundary evidence around the likely subject.", np.clip(silhouette, 0, 1)))
    return features


def interpret_focus_description(text: str) -> FocusIntent:
    """Map supported plain-language keywords without claiming scene semantics."""
    lowered = text.lower(); intent = FocusIntent(); messages: list[str] = []
    if any(word in lowered for word in ("face", "eyes", "hair")): intent.add_types.add("face"); messages.append("prioritise possible face regions")
    if any(word in lowered for word in ("outline", "silhouette", "people", "children", "subject", "dress", "clothing")): intent.add_types.update(("subject", "silhouette")); messages.append("prioritise likely subject and silhouette")
    reduce_background = any(word in lowered for word in ("ignore background", "abstract background", "simplify background", "ignore ceiling", "ignore lights"))
    reduce_background = reduce_background or ("ignore" in lowered and any(word in lowered for word in ("ceiling", "light", "background")))
    if reduce_background: intent.reduce_types.update(("background", "bright")); intent.background_amount = .9; messages.append("reduce background/bright candidates")
    elif any(word in lowered for word in ("keep background", "keep ceiling", "architecture")): intent.add_types.add("background"); intent.background_amount = .35; messages.append("retain prominent background structure")
    intent.explanation = "; ".join(messages) if messages else intent.explanation
    return intent
