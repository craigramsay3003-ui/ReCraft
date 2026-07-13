"""Preview quality and camera-independent geometry settings."""

from dataclasses import dataclass
from enum import Enum


class PreviewQuality(str, Enum):
    FAST = "Fast"
    BALANCED = "Balanced"
    FINAL = "Final"


@dataclass(frozen=True)
class PreviewSettings:
    """Explicit preview reductions; final export ignores them."""

    quality: PreviewQuality = PreviewQuality.BALANCED

    @property
    def analysis_maximum(self) -> int:
        return {PreviewQuality.FAST: 600, PreviewQuality.BALANCED: 1000, PreviewQuality.FINAL: 1600}[self.quality]

    @property
    def mesh_resolution_scale(self) -> float:
        return {PreviewQuality.FAST: .45, PreviewQuality.BALANCED: .7, PreviewQuality.FINAL: 1.0}[self.quality]
