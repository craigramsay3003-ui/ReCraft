"""Registry of available procedural styles."""

from collections.abc import Iterator

from recraft.styles import ContourStyle, FragmentStyle, HalftoneStyle
from recraft.styles.base import ArtStyle


class StyleRegistry:
    """Store and retrieve styles by stable identifier."""

    def __init__(self) -> None:
        self._styles: dict[str, ArtStyle] = {}

    def register(self, style: ArtStyle) -> None:
        """Register *style*, rejecting duplicate identifiers."""
        if not style.identifier:
            raise ValueError("A style identifier cannot be empty")
        if style.identifier in self._styles:
            raise ValueError(f"Style already registered: {style.identifier}")
        self._styles[style.identifier] = style

    def get(self, identifier: str) -> ArtStyle:
        """Return a style or raise a useful error."""
        try:
            return self._styles[identifier]
        except KeyError as exc:
            raise KeyError(f"Unknown style: {identifier}") from exc

    def __iter__(self) -> Iterator[ArtStyle]:
        return iter(self._styles.values())


def create_default_registry() -> StyleRegistry:
    """Create a registry containing all built-in styles."""
    registry = StyleRegistry()
    for style in (ContourStyle(), HalftoneStyle(), FragmentStyle()):
        registry.register(style)
    return registry
