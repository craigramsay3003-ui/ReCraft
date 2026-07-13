"""Central physical-output presets for the simplified ReCraft workflow."""

from dataclasses import dataclass
from enum import Enum


class ReliefStyle(str, Enum):
    """Three understandable physical relief modes."""

    PORTRAIT = "Portrait Relief"
    GRAPHIC = "Graphic Relief"
    LAYERED = "Layered Relief"


@dataclass(frozen=True)
class ReliefPreset:
    """Image interpretation choices hidden behind one physical style."""

    style: ReliefStyle
    description: str
    smoothing: float
    tonal_weight: float
    edge_weight: float
    contrast_weight: float
    subject_weight: float
    background_suppression: float
    height_levels: int = 0


RELIEF_PRESETS = {
    ReliefStyle.PORTRAIT: ReliefPreset(ReliefStyle.PORTRAIT, "Shallow facial and silhouette detail with a subdued background.", 2.2, .62, .18, .12, .38, .78, 0),
    ReliefStyle.GRAPHIC: ReliefPreset(ReliefStyle.GRAPHIC, "Clean poster-like tonal shapes with reinforced structural edges.", 3.0, .58, .28, .14, .18, .45, 7),
    ReliefStyle.LAYERED: ReliefPreset(ReliefStyle.LAYERED, "Five broad printable height bands for bold physical regions.", 4.0, .78, .08, .08, .12, .55, 5),
}


@dataclass(frozen=True)
class ReliefSettings:
    """Small validated configuration shared by preview and export."""

    style: ReliefStyle = ReliefStyle.PORTRAIT
    physical_width_mm: float = 160.0
    relief_depth_mm: float = 1.8
    base_thickness_mm: float = 1.5
    background_strength: float = .65
    subject_emphasis: float = .65
    relief_contrast: float = 1.0
    minimum_feature_mm: float = .8
    invert: bool = False
    preview_resolution: int = 150
    export_resolution: int = 260
    nozzle_diameter_mm: float = .4
    layer_height_mm: float = .2

    def validated(self) -> "ReliefSettings":
        """Reject unsafe physical and memory-heavy combinations."""
        if not 40 <= self.physical_width_mm <= 500: raise ValueError("Physical width must be between 40 and 500 mm")
        if not .5 <= self.relief_depth_mm <= 5: raise ValueError("Relief depth must be between 0.5 and 5 mm")
        if not .8 <= self.base_thickness_mm <= 8: raise ValueError("Base thickness must be between 0.8 and 8 mm")
        if not 0 <= self.background_strength <= 1: raise ValueError("Background strength must be between 0 and 1")
        if not 0 <= self.subject_emphasis <= 1: raise ValueError("Subject emphasis must be between 0 and 1")
        if not .5 <= self.relief_contrast <= 2: raise ValueError("Relief contrast must be between 0.5 and 2")
        if self.minimum_feature_mm < max(.4, self.nozzle_diameter_mm * 1.5): raise ValueError("Minimum feature width is too small for the selected nozzle")
        if not 64 <= self.preview_resolution <= 220: raise ValueError("Preview quality must be between 64 and 220 samples")
        if not 120 <= self.export_resolution <= 360: raise ValueError("Export quality must be between 120 and 360 samples")
        if self.relief_depth_mm < self.layer_height_mm * 3: raise ValueError("Relief depth should span at least three printable layers")
        return self
