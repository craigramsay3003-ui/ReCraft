"""Central creative presets for the preview-led Contour workflow."""

from dataclasses import dataclass, field, replace
from enum import Enum


class ContourPresetName(str, Enum):
    """Primary user-facing creative choices."""

    DETAILED = "Detailed"
    STANDARD = "Standard"
    ABSTRACT = "Abstract"


@dataclass(frozen=True)
class ContourPreset:
    """A meaningful group of art, relief, and preview defaults."""

    name: ContourPresetName
    description: str
    detail: int
    smoothing: float
    simplification: float
    minimum_path_length: float
    minimum_spacing: float
    line_weight: int
    subject_emphasis: float
    background_reduction: float
    ridge_width: float
    minimum_height: float
    maximum_height: float
    relief_strength: float
    mesh_resolution: int
    analysis_maximum: int


PRESETS: dict[ContourPresetName, ContourPreset] = {
    ContourPresetName.DETAILED: ContourPreset(ContourPresetName.DETAILED, "Preserves fine subject structure with printable narrow ridges.", 24, 1.2, .45, 7, 2.5, 1, .95, .45, .9, .3, 2.2, 1.35, 230, 1600),
    ContourPresetName.STANDARD: ContourPreset(ContourPresetName.STANDARD, "Balanced recognisability, background control, and reliable printing.", 15, 2.0, 1.0, 12, 5, 2, .75, .65, 1.2, .4, 1.8, 1.0, 160, 1200),
    ContourPresetName.ABSTRACT: ContourPreset(ContourPresetName.ABSTRACT, "Broad silhouettes and tonal regions with strongly simplified background.", 8, 3.4, 2.8, 24, 9, 3, .8, .9, 1.8, .6, 1.6, .8, 100, 900),
}


@dataclass
class PresetState:
    """Track selected preset and whether controls diverged from it."""

    selected: ContourPresetName = ContourPresetName.STANDARD
    current: ContourPreset = field(default_factory=lambda: PRESETS[ContourPresetName.STANDARD])

    @property
    def modified(self) -> bool:
        """Return whether current values differ from the selected preset."""
        return self.current != PRESETS[self.selected]

    def select(self, name: ContourPresetName) -> ContourPreset:
        """Select and reset to a preset."""
        self.selected = name; self.current = PRESETS[name]; return self.current

    def reset(self) -> ContourPreset:
        """Restore the selected preset's exact values."""
        self.current = PRESETS[self.selected]; return self.current

    def modify(self, **changes: object) -> ContourPreset:
        """Record manual changes for modified-state feedback."""
        self.current = replace(self.current, **changes); return self.current
