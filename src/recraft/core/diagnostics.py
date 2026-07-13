"""Crash logging and structured pipeline timing diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path

from recraft.core.paths import user_data_directory


@dataclass(frozen=True)
class PipelineMetrics:
    """Safe, non-image metadata recorded for one render or mesh operation."""

    preset: str
    source_resolution: tuple[int, int]
    output_resolution: tuple[int, int]
    retained_paths: int = 0
    sampled_points: int = 0
    vertices: int = 0
    faces: int = 0
    estimated_mesh_memory_mb: float = 0.0
    backend: str = "Qt software mesh viewer"
    stage_seconds: dict[str, float] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def summary(self) -> str:
        """Return a compact human-readable diagnostic line."""
        stages = ", ".join(f"{name}={seconds:.3f}s" for name, seconds in self.stage_seconds.items())
        return (
            f"preset={self.preset}; source={self.source_resolution}; output={self.output_resolution}; "
            f"paths={self.retained_paths}; points={self.sampled_points}; vertices={self.vertices}; "
            f"faces={self.faces}; memory={self.estimated_mesh_memory_mb:.1f}MB; "
            f"backend={self.backend}; {stages}"
        )


def diagnostic_log_path() -> Path:
    """Return the persistent local crash/diagnostic log path."""
    return user_data_directory(create=True) / "recraft.log"


def get_diagnostic_logger() -> logging.Logger:
    """Return ReCraft's rotating-safe process logger without image content."""
    logger = logging.getLogger("recraft")
    if not logger.handlers:
        handler = logging.FileHandler(diagnostic_log_path(), encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler); logger.setLevel(logging.INFO); logger.propagate = False
    return logger
