# ReCraft

**Create the impossible.**

ReCraft transforms ordinary images into mathematically generated artwork that would be difficult or unrealistic to design by hand. It is being developed as both a creative tool and a learning project, with the eventual goal of producing distinctive one-off physical art prints.

## What ReCraft is

ReCraft is an early experimental desktop prototype for interpreting images as procedural artwork. It is more than a collection of filters: each style rebuilds source structure using a different mathematical visual language.

## Current prototype features

- Load common image formats and compare the original with a generated preview.
- Contour, Halftone, and Fragment procedural styles.
- Style-specific controls generated from reusable style metadata.
- PNG export and a processing API independent of the interface.

Version 0.1 produces 2D images only.

## Example workflow

1. Select **Open Image** and choose a photograph.
2. Choose a style and adjust its parameters.
3. Select **Generate** to create a preview.
4. Select **Save Output** to export a PNG.

## Installation

Python 3.11 or newer is required.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
python -m pip install -e .
```

## Running the application

```bash
recraft
# or
python -m recraft
```

## Running tests

```bash
python -m pip install -e ".[dev]"
pytest
```

## Project structure

Processing code lives in `src/recraft/core` and `src/recraft/styles`; the PySide6 interface lives in `src/recraft/ui`. Tests and design documentation are kept in `tests` and `docs`.

## Adding a new art style

Subclass `ArtStyle`, declare metadata and parameter definitions, implement `process`, then register one instance in `create_default_registry`. No UI changes are required. See `docs/ARCHITECTURE.md`.

## Roadmap

Future work may include vector and SVG exports, procedural line and flow styles, depth maps, relief meshes, and manufacturable STL and 3MF output. See `docs/ROADMAP.md`.

## Project status

This is an early experimental prototype intended to validate the architecture and learn from generated results. APIs and output may change. ReCraft is not affiliated with HueForge or any other existing software.

## Licence

MIT. See `LICENSE`.
