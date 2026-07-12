"""Testable camera model for the interactive relief viewer."""

from dataclasses import dataclass
from enum import Enum

import numpy as np


class ProjectionMode(str, Enum):
    PERSPECTIVE = "Perspective"
    ORTHOGRAPHIC = "Orthographic"


@dataclass
class MeshCamera:
    """Orbit, pan, zoom, and standard-view state without geometry mutation."""

    yaw: float = -35
    pitch: float = 55
    distance: float = 2.6
    pan_x: float = 0
    pan_y: float = 0
    projection: ProjectionMode = ProjectionMode.PERSPECTIVE

    def reset(self) -> None:
        self.yaw, self.pitch, self.distance, self.pan_x, self.pan_y = -35, 55, 2.6, 0, 0

    def orbit(self, dx: float, dy: float) -> None:
        self.yaw = (self.yaw + dx) % 360; self.pitch = float(np.clip(self.pitch + dy, -89, 89))

    def zoom(self, amount: float) -> None:
        self.distance = float(np.clip(self.distance * amount, .6, 12))

    def pan(self, dx: float, dy: float) -> None:
        self.pan_x += dx; self.pan_y += dy

    def set_view(self, name: str) -> None:
        views = {"Front": (0, 0), "Back": (180, 0), "Left": (-90, 0), "Right": (90, 0), "Top": (0, 89), "Bottom": (0, -89), "Perspective": (-35, 55)}
        if name not in views: raise ValueError(f"Unknown camera view: {name}")
        self.yaw, self.pitch = views[name]

    def project(self, vertices: np.ndarray, viewport: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
        """Project normalized mesh vertices and return screen points plus depth."""
        points = np.asarray(vertices, np.float64); centre = (points.min(axis=0) + points.max(axis=0)) / 2; span = max(float(np.ptp(points, axis=0).max()), 1e-6)
        points = (points - centre) / span
        yaw, pitch = np.deg2rad(self.yaw), np.deg2rad(self.pitch)
        rz = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])
        rx = np.array([[1, 0, 0], [0, np.cos(pitch), -np.sin(pitch)], [0, np.sin(pitch), np.cos(pitch)]])
        rotated = points @ rz.T @ rx.T; width, height = viewport
        if self.projection is ProjectionMode.PERSPECTIVE:
            factor = 1 / np.maximum(self.distance - rotated[:, 2], .15)
        else: factor = np.full(len(points), 1 / self.distance)
        scale = min(width, height) * 1.65
        screen = np.column_stack((width / 2 + (rotated[:, 0] * factor + self.pan_x) * scale, height / 2 - (rotated[:, 1] * factor + self.pan_y) * scale))
        return screen, rotated[:, 2]
