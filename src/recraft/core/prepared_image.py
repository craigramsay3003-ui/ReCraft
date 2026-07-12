"""Pipeline helpers joining image preparation to style processing."""

from collections.abc import Mapping

from PIL import Image

from recraft.core.image_transform import ImageTransformSettings, prepare_image
from recraft.styles.base import ArtStyle, ParameterValue
from recraft.engine import analyse_image
from recraft.engine.analysis_result import ImageAnalysis
from recraft.engine.user_importance import UserImportanceState, apply_user_importance


def preview_size(settings: ImageTransformSettings, maximum: int = 800) -> tuple[int, int]:
    """Return a preview size preserving the configured export aspect ratio."""
    state = settings.validated()
    scale = min(1.0, maximum / max(state.output_width, state.output_height))
    return max(1, round(state.output_width * scale)), max(1, round(state.output_height * scale))


def render_prepared_preview(
    source: Image.Image, settings: ImageTransformSettings, maximum: int = 800
) -> Image.Image:
    """Render a prepared working canvas at interactive preview resolution."""
    return prepare_image(source, settings, preview_size(settings, maximum))


def render_style_preview(
    source: Image.Image,
    settings: ImageTransformSettings,
    style: ArtStyle,
    parameters: Mapping[str, ParameterValue] | None = None,
    maximum: int = 800,
    user_importance: UserImportanceState | None = None,
) -> Image.Image:
    """Prepare at preview resolution and pass that canvas to a style."""
    analysis = analyse_image(render_prepared_preview(source, settings, maximum))
    analysis = apply_user_importance(analysis, user_importance, settings)
    return style.process(analysis, parameters)


def render_style_export(
    source: Image.Image,
    settings: ImageTransformSettings,
    style: ArtStyle,
    parameters: Mapping[str, ParameterValue] | None = None,
    user_importance: UserImportanceState | None = None,
) -> Image.Image:
    """Prepare and process directly at configured full export resolution."""
    prepared = prepare_image(source, settings)
    analysis = analyse_image(prepared)
    analysis = apply_user_importance(analysis, user_importance, settings)
    return style.process(analysis, parameters)


def analyse_prepared_preview(
    source: Image.Image, settings: ImageTransformSettings, maximum: int = 800,
    user_importance: UserImportanceState | None = None,
) -> ImageAnalysis:
    """Prepare and analyse one interactive working canvas."""
    analysis = analyse_image(render_prepared_preview(source, settings, maximum))
    return apply_user_importance(analysis, user_importance, settings)
