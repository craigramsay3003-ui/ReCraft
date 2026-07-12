import pytest

from recraft.core.style_registry import StyleRegistry, create_default_registry
from recraft.styles.contour import ContourStyle


def test_registered_styles_have_required_metadata() -> None:
    styles = list(create_default_registry())
    assert {style.identifier for style in styles} == {"contour", "halftone", "fragment"}
    for style in styles:
        assert style.identifier and style.display_name and style.description
        assert style.parameters


def test_registry_rejects_duplicate_identifier() -> None:
    registry = StyleRegistry()
    registry.register(ContourStyle())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(ContourStyle())
