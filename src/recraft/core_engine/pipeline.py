"""The reusable ReCraft core: interpretation, design, colour, and relief."""

from dataclasses import replace
from time import perf_counter
from typing import Callable

import cv2
import numpy as np
from PIL import Image

from recraft.core_engine.colour import build_colour_map
from recraft.core_engine.models import (
    ArtisticSimplificationData,
    BackgroundTreatment,
    CoreRenderResult,
    CoreSettings,
    DetailLevel,
    FeatureImportanceData,
    PreparedImageData,
    ReliefFieldData,
    ReliefMeshData,
    SubjectAnalysisData,
    SubjectEmphasis,
)
from recraft.engine import analyse_image
from recraft.relief.mesh import build_relief_mesh
from recraft.relief.presets import ReliefSettings, ReliefStyle


def _readonly(array: np.ndarray, dtype: np.dtype | None = np.float32) -> np.ndarray:
    result = np.asarray(array, dtype=dtype).copy()
    result.flags.writeable = False
    return result


def prepare_core_image(image: Image.Image, settings: CoreSettings) -> PreparedImageData:
    """Wrap already composed pixels with explicit transform metadata."""
    state = settings.validated()
    pixels = image.convert("RGB").copy()
    transform = np.eye(3, dtype=np.float64)
    transform.flags.writeable = False
    return PreparedImageData(
        pixels,
        pixels.width / pixels.height,
        (0, 0, 1, 1),
        0,
        transform,
        state.preview_resolution,
        state.export_resolution,
    )


def _largest_supported_subject(rgb: np.ndarray, centre: np.ndarray) -> tuple[np.ndarray, float, str]:
    """Find a coherent foreground region using simple-background evidence."""
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    border = max(2, round(min(rgb.shape[:2]) * .06))
    samples = np.concatenate(
        (lab[:border].reshape(-1, 3), lab[-border:].reshape(-1, 3), lab[:, :border].reshape(-1, 3), lab[:, -border:].reshape(-1, 3)),
        axis=0,
    )
    background_colour = np.median(samples, axis=0)
    distance = np.linalg.norm(lab - background_colour, axis=2)
    threshold = max(10.0, float(np.percentile(distance, 42)))
    candidate = np.asarray(distance > threshold, np.uint8)
    kernel_size = max(3, round(min(rgb.shape[:2]) * .025) | 1)
    kernel = np.ones((kernel_size, kernel_size), np.uint8)
    candidate = cv2.morphologyEx(candidate, cv2.MORPH_CLOSE, kernel)
    candidate = cv2.morphologyEx(candidate, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    count, components, statistics, centroids = cv2.connectedComponentsWithStats(candidate, 8)
    best = 0
    best_score = 0.0
    for component in range(1, count):
        area = statistics[component, cv2.CC_STAT_AREA]
        if area < candidate.size * .02:
            continue
        x = int(np.clip(round(centroids[component, 0]), 0, centre.shape[1] - 1))
        y = int(np.clip(round(centroids[component, 1]), 0, centre.shape[0] - 1))
        score = area * (.4 + .6 * float(centre[y, x]))
        if score > best_score:
            best, best_score = component, score
    if best:
        mask = np.asarray(components == best, np.float32)
        coverage = float(mask.mean())
        confidence = float(np.clip(1 - abs(coverage - .45), .25, .9))
        return mask, confidence, "largest coherent foreground region"
    return np.asarray(centre > .22, np.float32), .2, "centre-weighted fallback"


def analyse_subject(prepared: PreparedImageData, resolution: int) -> SubjectAnalysisData:
    """Extract bounded subject evidence with an explicit fallback state."""
    scale = resolution / max(prepared.pixels.size)
    size = (max(48, round(prepared.pixels.width * scale)), max(48, round(prepared.pixels.height * scale)))
    image = prepared.pixels.resize(size, Image.Resampling.LANCZOS)
    analysis = analyse_image(image)
    rgb = np.asarray(image, np.uint8)
    coherent, confidence, fallback = _largest_supported_subject(rgb, analysis.centre_weight)
    automatic = np.asarray(analysis.subject_mask, np.float32)
    subject = np.clip(.75 * coherent + .25 * automatic, 0, 1)
    subject = cv2.GaussianBlur(subject, (0, 0), 1.2)
    subject = np.clip(subject, 0, 1)
    silhouette = cv2.morphologyEx(np.asarray(subject > .45, np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)).astype(np.float32)
    colour_regions = np.asarray(analysis.colour_labels, np.int32)
    faces = tuple(tuple(map(int, rectangle)) for rectangle in analysis.face_rectangles)
    return SubjectAnalysisData(
        _readonly(subject),
        _readonly(1 - subject),
        _readonly(analysis.face_mask),
        faces,
        _readonly(silhouette),
        _readonly(analysis.gradient_magnitude),
        _readonly(analysis.local_contrast),
        _readonly(analysis.greyscale),
        _readonly(colour_regions, np.int32),
        _readonly(analysis.centre_weight),
        confidence,
        fallback,
    )


def build_feature_importance(analysis: SubjectAnalysisData, settings: CoreSettings) -> FeatureImportanceData:
    """Combine subject, silhouette, faces, and useful internal boundaries."""
    state = settings.validated()
    subject_weight = {SubjectEmphasis.LOW: .45, SubjectEmphasis.MEDIUM: .65, SubjectEmphasis.HIGH: .82}[SubjectEmphasis(state.subject_emphasis)]
    background_reduction = {BackgroundTreatment.REMOVE: .92, BackgroundTreatment.SIMPLIFY: .68, BackgroundTreatment.KEEP: .35}[BackgroundTreatment(state.background)]
    internal = analysis.edges * (.35 + .65 * analysis.subject_mask)
    values = (
        subject_weight * analysis.subject_mask
        + .22 * analysis.silhouette
        + .16 * internal
        + .12 * analysis.local_contrast * analysis.subject_mask
        + .22 * analysis.face_mask
        + .08 * analysis.centre_weighting
    )
    values *= 1 - analysis.background_mask * background_reduction * .65
    low, high = np.percentile(values, (1, 99))
    values = np.zeros_like(values) if high - low < 1e-8 else np.clip((values - low) / (high - low), 0, 1)
    return FeatureImportanceData(_readonly(values), subject_weight, background_reduction)


def simplify_artwork(
    analysis: SubjectAnalysisData,
    importance: FeatureImportanceData,
    settings: CoreSettings,
) -> ArtisticSimplificationData:
    """Merge tones, remove sub-print detail, and retain meaningful edges."""
    state = settings.validated()
    detail = DetailLevel(state.detail)
    sigma = {DetailLevel.SIMPLE: 4.5, DetailLevel.BALANCED: 2.8, DetailLevel.FINE: 1.7}[detail]
    levels = {DetailLevel.SIMPLE: 4, DetailLevel.BALANCED: 6, DetailLevel.FINE: 9}[detail]
    broad = cv2.GaussianBlur(analysis.luminance, (0, 0), sigma)
    broad = cv2.bilateralFilter(broad.astype(np.float32), 7, .18, 7)
    tonal = np.round(np.clip(broad, 0, 1) * (levels - 1)) / (levels - 1)
    mm_per_pixel = state.physical_width_mm / max(analysis.luminance.shape[1] - 1, 1)
    multiplier = {DetailLevel.SIMPLE: 1.5, DetailLevel.BALANCED: 1.0, DetailLevel.FINE: .75}[detail]
    minimum_pixels = max(1, round(state.minimum_feature_mm * multiplier / mm_per_pixel))
    kernel = np.ones((minimum_pixels | 1, minimum_pixels | 1), np.uint8)
    subject = cv2.morphologyEx(np.asarray(analysis.subject_mask > .4, np.uint8), cv2.MORPH_CLOSE, kernel).astype(np.float32)
    edge_threshold = {DetailLevel.SIMPLE: .46, DetailLevel.BALANCED: .34, DetailLevel.FINE: .25}[detail]
    reinforced = np.asarray(analysis.edges * importance.values > edge_threshold, np.float32)
    reinforced = cv2.morphologyEx(reinforced, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    reinforced *= np.clip(subject + analysis.silhouette, 0, 1)
    return ArtisticSimplificationData(
        _readonly(broad),
        _readonly(tonal),
        _readonly(reinforced),
        _readonly(subject),
        minimum_pixels,
    )


def design_relief_field(
    analysis: SubjectAnalysisData,
    importance: FeatureImportanceData,
    simplification: ArtisticSimplificationData,
    settings: CoreSettings,
) -> ReliefFieldData:
    """Turn simplified forms into a deliberately constrained positive relief."""
    state = settings.validated()
    treatment = BackgroundTreatment(state.background)
    background_scale = {BackgroundTreatment.REMOVE: .015, BackgroundTreatment.SIMPLIFY: .10, BackgroundTreatment.KEEP: .22}[treatment]
    background = background_scale * cv2.GaussianBlur(simplification.tonal_regions, (0, 0), 5)
    subject = simplification.simplified_subject
    broad_form = .24 + .48 * simplification.tonal_regions
    structural = .18 * simplification.reinforced_edges + .10 * importance.values
    values = background * (1 - subject) + subject * (broad_form + structural)
    values += analysis.silhouette * subject * .10
    values = cv2.GaussianBlur(values.astype(np.float32), (0, 0), .65)
    if np.any(subject > .5):
        subject_values = values[subject > .5]
        low, high = np.percentile(subject_values, (2, 98))
        if high - low > 1e-8:
            normalized_subject = np.clip((values - low) / (high - low), 0, 1)
            values = values * (1 - subject) + (.18 + .82 * normalized_subject) * subject
    values = np.clip(values, 0, 1)
    if state.invert:
        values = 1 - values
    warnings: list[str] = []
    if state.minimum_feature_mm < state.nozzle_diameter_mm * 2:
        warnings.append("Fine features approach the selected nozzle width; inspect the slice.")
    if state.physical_width_mm < 100 and state.detail is DetailLevel.FINE:
        warnings.append("Increase physical width or use Balanced detail for printable facial features.")
    subject_values = values[subject > .5]
    background_values = values[subject <= .5]
    subject_range = (
        (float(subject_values.min()), float(subject_values.max()))
        if subject_values.size else (0.0, 0.0)
    )
    background_range = (
        (float(background_values.min()), float(background_values.max()))
        if background_values.size else (0.0, 0.0)
    )
    return ReliefFieldData(
        _readonly(values),
        0.0,
        subject_range,
        background_range,
        .18,
        state.physical_width_mm,
        state.relief_depth_mm,
        state.invert,
        tuple(warnings),
    )


def build_core_mesh(relief: ReliefFieldData, colour, settings: CoreSettings, preview: bool) -> ReliefMeshData:
    """Create the shared oriented mesh and aligned UV coordinates."""
    state = settings.validated()
    mesh_settings = ReliefSettings(
        style=ReliefStyle.PORTRAIT,
        physical_width_mm=state.physical_width_mm,
        relief_depth_mm=state.relief_depth_mm,
        base_thickness_mm=state.base_thickness_mm,
        minimum_feature_mm=state.minimum_feature_mm,
        preview_resolution=state.preview_resolution,
        export_resolution=state.export_resolution,
        nozzle_diameter_mm=state.nozzle_diameter_mm,
        layer_height_mm=state.layer_height_mm,
    )
    result = build_relief_mesh(relief.values, mesh_settings, preview=preview)
    vertices = np.asarray(result.mesh.vertices)
    uv = np.column_stack((vertices[:, 0] / result.width_mm, 1 - vertices[:, 1] / result.height_mm))
    return ReliefMeshData(result, _readonly(np.clip(uv, 0, 1), np.float64), colour, "preview" if preview else "export")


def render_core(
    image: Image.Image,
    settings: CoreSettings,
    *,
    preview: bool = True,
    stage_callback: Callable[[str, int], None] | None = None,
) -> CoreRenderResult:
    """Run the complete UI-independent ReCraft Portrait Relief pipeline."""
    state = settings.validated()
    timings: dict[str, float] = {}
    started = perf_counter()
    notify = stage_callback or (lambda _name, _progress: None)
    notify("Preparing image", 5)
    prepared = prepare_core_image(image, state)
    timings["prepare"] = perf_counter() - started
    resolution = state.preview_resolution if preview else state.export_resolution
    notify("Analysing subject", 18)
    stage = perf_counter(); analysis = analyse_subject(prepared, resolution); timings["subject_analysis"] = perf_counter() - stage
    notify("Building feature importance", 30)
    stage = perf_counter(); importance = build_feature_importance(analysis, state); timings["importance"] = perf_counter() - stage
    notify("Simplifying artwork", 42)
    stage = perf_counter(); simplification = simplify_artwork(analysis, importance, state); timings["simplification"] = perf_counter() - stage
    notify("Creating relief", 58)
    stage = perf_counter(); relief = design_relief_field(analysis, importance, simplification, state); timings["relief"] = perf_counter() - stage
    size = (relief.values.shape[1], relief.values.shape[0])
    notify("Mapping colour", 72)
    stage = perf_counter(); colour = build_colour_map(prepared.pixels, state, size, max(4, simplification.minimum_feature_pixels**2)); timings["colour"] = perf_counter() - stage
    notify("Building preview" if preview else "Building export", 84)
    stage = perf_counter(); mesh = build_core_mesh(relief, colour, state, preview); timings["mesh"] = perf_counter() - stage
    timings["total"] = perf_counter() - started
    return CoreRenderResult(prepared, analysis, importance, simplification, relief, colour, mesh, timings)
