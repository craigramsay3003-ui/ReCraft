"""Platform-appropriate application data paths."""

import os
from pathlib import Path


def user_data_directory(create: bool = False) -> Path:
    """Return ReCraft's per-user data directory, optionally creating it."""
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    result = root / "ReCraft"
    if create:
        result.mkdir(parents=True, exist_ok=True)
    return result
