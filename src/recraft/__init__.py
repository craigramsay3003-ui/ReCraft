"""ReCraft procedural-art application."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("recraft-art")
except PackageNotFoundError:  # source tree without installation metadata
    __version__ = "0+unknown"
