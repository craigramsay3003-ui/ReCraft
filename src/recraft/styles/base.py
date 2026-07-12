"""Contracts shared by procedural art styles."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Mapping

from PIL import Image

ParameterValue = int | float


@dataclass(frozen=True)
class Parameter:
    """Describe one numeric style control."""

    key: str
    label: str
    default: ParameterValue
    minimum: ParameterValue
    maximum: ParameterValue
    step: ParameterValue = 1


class ArtStyle(ABC):
    """Abstract interface implemented by all ReCraft styles."""

    identifier: str
    display_name: str
    description: str
    parameters: tuple[Parameter, ...]

    def defaults(self) -> dict[str, ParameterValue]:
        """Return default parameter values."""
        return {item.key: item.default for item in self.parameters}

    def validate_parameters(
        self, values: Mapping[str, ParameterValue] | None = None
    ) -> dict[str, ParameterValue]:
        """Merge defaults and validate known numeric parameters."""
        result = self.defaults()
        supplied = dict(values or {})
        unknown = supplied.keys() - result.keys()
        if unknown:
            raise ValueError(f"Unknown parameter(s): {', '.join(sorted(unknown))}")
        result.update(supplied)
        for definition in self.parameters:
            value = result[definition.key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{definition.label} must be a number")
            if not definition.minimum <= value <= definition.maximum:
                raise ValueError(
                    f"{definition.label} must be between "
                    f"{definition.minimum} and {definition.maximum}"
                )
        return result

    @abstractmethod
    def process(
        self, image: Image.Image, parameters: Mapping[str, ParameterValue] | None = None
    ) -> Image.Image:
        """Return a procedural interpretation of *image*."""
