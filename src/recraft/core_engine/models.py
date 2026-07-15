"""Typed contracts for the ReCraft photograph-to-artwork core pipeline."""

from dataclasses import dataclass
from enum import Enum

import numpy as np
from PIL import Image

from recraft.relief.mesh import ReliefMeshResult


class SubjectEmphasis(str, Enum):
    """How strongly the likely subject is separated from its surroundings."""

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class BackgroundTreatment(str, Enum):
    """Amount of broad background structure retained in the artwork."""

    REMOVE = "Remove"
    SIMPLIFY = "Simplify"
    KEEP = "Keep"


class DetailLevel(str, Enum):
    """Print-aware artistic detail choice."""

    SIMPLE = "Simple"
    BALANCED = "Balanced"
    FINE = "Fine"


class ColourMode(str, Enum):
    """Independent surface-colour representation."""

    ORIGINAL = "Original Colour"
    ARTISTIC = "Artistic Palette"
    MONOCHROME = "Monochrome Material"


class MonochromeMaterial(str, Enum):
    """Matte preview materials that do not imply glossy output."""

    MATTE_WHITE = "Matte white"
    STONE = "Stone"
    WARM_GREY = "Warm grey"
    BLACK = "Black"
    CUSTOM = "Custom colour"


@dataclass(frozen=True)
class CoreSettings:
    """Small set of creative and physical choices for Portrait Relief."""

    subject_emphasis: SubjectEmphasis | str = SubjectEmphasis.MEDIUM
    background: BackgroundTreatment | str = BackgroundTreatment.SIMPLIFY
    detail: DetailLevel | str = DetailLevel.BALANCED
    colour_mode: ColourMode | str = ColourMode.MONOCHROME
    palette_size: int = 4
    locked_palette: tuple[str | None, ...] = ()
    monochrome_material: MonochromeMaterial | str = MonochromeMaterial.STONE
    custom_material_colour: str = "#A59D90"
    physical_width_mm: float = 160.0
    relief_depth_mm: float = 1.8
    base_thickness_mm: float = 1.5
    nozzle_diameter_mm: float = .4
    layer_height_mm: float = .2
    minimum_feature_mm: float = .8
    preview_resolution: int = 190
    export_resolution: int = 290
    invert: bool = False

    def validated(self) -> "CoreSettings":
        """Return a normalized configuration or raise an actionable error."""
        from dataclasses import replace
        import re

        try:
            subject = SubjectEmphasis(self.subject_emphasis)
            background = BackgroundTreatment(self.background)
            detail = DetailLevel(self.detail)
            colour = ColourMode(self.colour_mode)
            material = MonochromeMaterial(self.monochrome_material)
        except ValueError as exc:
            raise ValueError(f"Unknown ReCraft creative setting: {exc}") from exc
        if not 2 <= self.palette_size <= 6:
            raise ValueError("Palette size must be between 2 and 6 colours")
        if not 40 <= self.physical_width_mm <= 500:
            raise ValueError("Physical width must be between 40 and 500 mm")
        if not .5 <= self.relief_depth_mm <= 5:
            raise ValueError("Relief depth must be between 0.5 and 5 mm")
        if not .8 <= self.base_thickness_mm <= 8:
            raise ValueError("Base thickness must be between 0.8 and 8 mm")
        if self.minimum_feature_mm < self.nozzle_diameter_mm * 1.5:
            raise ValueError("Minimum feature width is too small for the selected nozzle")
        if self.relief_depth_mm < self.layer_height_mm * 3:
            raise ValueError("Relief depth should span at least three selected layers")
        if not 96 <= self.preview_resolution <= 240 or not 160 <= self.export_resolution <= 290:
            raise ValueError("Preview or export quality is outside safe limits")
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", self.custom_material_colour):
            raise ValueError("Custom material colour must use #RRGGBB")
        locks = tuple(self.locked_palette[: self.palette_size])
        if any(value is not None and not re.fullmatch(r"#[0-9A-Fa-f]{6}", value) for value in locks):
            raise ValueError("Locked palette colours must use #RRGGBB")
        return replace(
            self,
            subject_emphasis=subject,
            background=background,
            detail=detail,
            colour_mode=colour,
            monochrome_material=material,
            locked_palette=locks,
        )


@dataclass(frozen=True)
class PreparedImageData:
    """Prepared pixels plus reproducible source-to-output metadata."""

    pixels: Image.Image
    aspect_ratio: float
    crop: tuple[float, float, float, float]
    orientation_degrees: int
    source_to_output: np.ndarray
    preview_resolution: int
    export_resolution: int


@dataclass(frozen=True)
class SubjectAnalysisData:
    """Honest bounded visual analysis without semantic certainty claims."""

    subject_mask: np.ndarray
    background_mask: np.ndarray
    face_mask: np.ndarray
    face_candidates: tuple[tuple[int, int, int, int], ...]
    silhouette: np.ndarray
    edges: np.ndarray
    local_contrast: np.ndarray
    luminance: np.ndarray
    colour_regions: np.ndarray
    centre_weighting: np.ndarray
    confidence: float
    fallback_state: str


@dataclass(frozen=True)
class FeatureImportanceData:
    """Normalized preservation priority used by artistic simplification."""

    values: np.ndarray
    subject_weight: float
    background_reduction: float


@dataclass(frozen=True)
class ArtisticSimplificationData:
    """Deliberately reduced broad form and retained structural features."""

    broad_tone: np.ndarray
    tonal_regions: np.ndarray
    reinforced_edges: np.ndarray
    simplified_subject: np.ndarray
    minimum_feature_pixels: int


@dataclass(frozen=True)
class ReliefFieldData:
    """Positive physical design field separated from mesh representation."""

    values: np.ndarray
    base_level: float
    subject_height_range: tuple[float, float]
    background_height_range: tuple[float, float]
    reinforced_feature_height: float
    physical_width_mm: float
    relief_depth_mm: float
    inverted: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ColourMapData:
    """Surface colour aligned with but independent from relief geometry."""

    pixels: np.ndarray
    labels: np.ndarray
    palette: tuple[str, ...]
    mode: ColourMode
    printable_palette: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ReliefMeshData:
    """Watertight relief geometry with stable colour coordinates."""

    result: ReliefMeshResult
    uv_coordinates: np.ndarray
    colour_map: ColourMapData
    quality: str


@dataclass(frozen=True)
class CoreRenderResult:
    """Complete reusable output of one ReCraft core interpretation."""

    prepared: PreparedImageData
    analysis: SubjectAnalysisData
    importance: FeatureImportanceData
    simplification: ArtisticSimplificationData
    relief: ReliefFieldData
    colour: ColourMapData
    mesh: ReliefMeshData
    stage_seconds: dict[str, float]
