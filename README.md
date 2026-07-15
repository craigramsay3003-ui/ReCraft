# ReCraft

**ReCraft interprets photographs and rebuilds them as distinctive printable artwork. Portrait Relief is the first physical style.**

## ReCraft Portrait Relief (experimental branch)

`feature/recraft-core-colour-relief` proves one focused workflow for a person,
pet, or vehicle against a simple background: open and frame the image, choose
Subject Emphasis, Background treatment, Detail, physical width and relief depth,
generate once, inspect the colour-mapped relief, then export STL or 3MF.

The persistent source and relief previews dominate a responsive workspace.
Colour can switch between Original Colour, a cleaned 2/3/4/6-colour Artistic
Palette, and matte Monochrome without rebuilding geometry. Advanced physical
settings are collapsed by default. See [ReCraft Core](docs/RECRAFT_CORE.md),
[Colour Relief](docs/COLOUR_RELIEF.md), and
[Benchmark Images](docs/BENCHMARK_IMAGES.md).

## Printable relief reset (experimental branch)

`feature/printable-relief-reset` replaces the exposed Contour application with
one focused workflow: open a photograph, choose a physical relief style,
generate a positive bas-relief plaque, inspect it, and export STL or 3MF. The
default interface contains one persistent source preview, one persistent 3D
preview, a compact control column, and one **Generate Relief** action. The old
Contour workspace remains in the source tree for reference but is not exposed
by the default application on this branch.

The three physical presets are:

- **Portrait Relief** — continuous shallow tone with restrained edge, subject,
  silhouette, and optional face emphasis; background evidence is reduced.
- **Graphic Relief** — seven cleaned height levels with stronger structural
  edges and poster-like tonal regions.
- **Layered Relief** — five broad height bands, stronger smoothing, and reduced
  fine texture for robust physical regions.

Normal relief is the default: the rear is flat at 0 mm, the solid base is the
lowest front surface, and image features project outward. A structured grid
creates the front, rear, and side walls as one deterministic watertight plaque.
Preview meshes are bounded to 150,000 triangles and exports to 350,000.

The default Bambu H2C test assumptions are a 0.4 mm nozzle, 0.2 mm layers,
160 mm width, 1.5 mm base, 1.8 mm relief depth, and 0.8 mm minimum feature.
They are conservative starting points, not a substitute for slicer inspection.
STL is the mandatory geometry-only output; 3MF currently contains the same
single printable object with one display colour. See
`docs/PRINTABLE_RELIEF_RESET.md`.

ReCraft transforms ordinary images into mathematically generated artwork that would be difficult or unrealistic to design by hand. It is being developed as both a creative tool and a learning project, with the eventual goal of producing distinctive one-off physical art prints.

## What ReCraft is

ReCraft is an early experimental desktop prototype for interpreting images as procedural artwork. It is more than a collection of filters: each style rebuilds source structure using a different mathematical visual language.

## ReCraft Engine

Before any style runs, the ReCraft Engine interprets the prepared image as
reusable "Image DNA". It extracts greyscale and contrast-enhanced images,
edges, gradients, colour clusters, texture, saliency, optional faces and
landmarks, generic subject/background masks, and centre weighting. These cues
produce a floating-point importance map where 0 permits aggressive
simplification and 1 requests maximum preservation.

Contour, Halftone, and Fragment all consume the same `ImageAnalysis` contract;
they no longer independently analyse raw pixels. The architecture also accepts
future importance, additive-brush, and subtractive-brush masks without
implementing painting tools yet.

Analysis maps are bounded to 1,200 pixels on their longest side for predictable
memory use. Styles resample only the maps they need onto the full export canvas.
Face detection is used when the installed OpenCV build exposes a compatible
detector. Landmark output is represented but remains empty without an installed
landmark model. No portrait assumption is used for subject detection.

## Current prototype features

- Load common image formats and compare the original with a generated preview.
- Non-destructively crop, pan, zoom, rotate, and flip before applying a style.
- Original, 1:1, 4:5, 2:3, 3:2, and 16:9 output framing with Fit or Fill.
- Independent preview and full-resolution export rendering.
- Background style rendering and PNG writing keep the interface responsive.
- A developer view can preview edges, importance, face/background/subject masks,
  saliency, colour clusters, and texture.

## User importance editing

The **Importance** panel lets the user override automatic analysis without
altering the source. Paint Add, Reduce, or Erase-to-automatic directly on the
prepared preview. Configure brush size/strength, automatic/user weighting,
background suppression, overlay visibility, or clear all edits. Masks use
source coordinates and stay aligned after crop, pan, zoom, rotation, flips,
preview resizing, and full-resolution export.

**Pick Colour** selects perceptually similar Lab colours with tolerance,
feather, and connected-only controls. **Pick Region** grows a connected visual
region. Preview either selection, then Add, Reduce, or Cancel. These are visual
selection tools, not semantic object recognition.

Developer views now include automatic/combined importance, add/reduce masks,
background suppression, selection previews, raw/filtered Contour paths, and
Contour path importance.

## Contour STL export

Contour produces reusable vector-like paths. The same result drives PNG and
raised-ridge STL output; lines are never re-detected from a PNG. Select Contour,
configure physical width, base thickness, ridge height/width, and border, then
choose **Export Contour STL**. ReCraft generates in the background, validates
watertightness, and reports millimetre dimensions, vertices, faces, and path.

STL currently supports Contour only. Inspect every STL in a slicer before
printing. ReCraft enforces a default 0.8 mm minimum ridge width, but the correct
minimum depends on printer and material.

## Preview-led Contour relief workflow

The tested five-page wizard has been replaced by one preview-led workspace. The
prepared/analysis image, 2D Contour result, and navigable actual 3D mesh remain
visible while compact collapsible controls change. Editable Image DNA focus
suggestions, manual importance tools, local keyword mapping, and Detailed,
Standard, and Abstract presets guide the workflow. Advanced controls are
collapsed by default.

The 3D viewer supports orbit, zoom, pan, fit/reset, standard views,
perspective/orthographic projection, and edge overlay. Bambu H2C and Custom
printer profiles provide editable nozzle/layer assumptions and printability
warnings. Fast/Balanced/Final preview quality never lowers export quality.

Choose independent Base and Contour colours for the shaded mesh preview. STL is
geometry-only; coloured 3MF stores Base and Contour Relief material assignments.
Mesh X preserves image left/right and image Y is converted to Cartesian Y. See
`docs/CONTOUR_WORKFLOW.md`.
- Contour, Halftone, and Fragment procedural styles.
- Style-specific controls generated from reusable style metadata.
- PNG export and a processing API independent of the interface.

Version 0.1 produces 2D images only.

## Example workflow

On `feature/printable-relief-reset`:

1. Select **Open Image**.
2. Choose **Fit full image** or **Crop to 4:5 plaque**.
3. Choose Portrait, Graphic, or Layered Relief.
4. Set physical width, relief depth, background reduction, and subject emphasis.
5. Select **Generate Relief** and keep inspecting the previous valid preview
   while work runs in the background.
6. Orbit with left-drag, pan with middle-drag or Shift-drag, and zoom with the
   wheel. Use Fit, Reset, Front, Perspective, or Orthographic when useful.
7. Export STL or 3MF. Export regenerates the model at export resolution; it does
   not upscale the preview mesh.

Advanced settings are collapsed by default and contain only preview/export
quality, contrast, base thickness, minimum feature, nozzle, layer height, and
explicit inversion.

The legacy style workflow below describes stable `main`, not the experimental
reset branch.

1. Select **Open Image** and choose a photograph. The imported source remains
   unchanged in memory.
2. In **Prepare Image**, choose an aspect ratio and output width/height. Use
   the fixed crop viewport with Fit or Fill, then zoom, drag to pan, rotate, or
   flip until the composition is right.
3. Choose a style and adjust its parameters.
4. Select **Generate Preview**. The style processes the prepared image, not the
   raw source.
5. Select **Save Full-Resolution PNG**. ReCraft regenerates the preparation and
   style at the configured export dimensions rather than upscaling the preview.

Reset restores a centred, unrotated, unflipped composition matching the source
dimensions. Output width and height must be positive and each is limited to
8,000 pixels to reduce the risk of accidental memory exhaustion.

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

## Building the Windows application

Install Inno Setup 6, then double-click `Build ReCraft.cmd`, or run the release
script from any directory:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_release.ps1
```

The repeatable build updates `.venv`, runs the full suite, creates the windowed
one-folder application at `dist/ReCraft/ReCraft.exe`, and creates
`dist/ReCraft-Setup.exe`. Existing generated outputs are safely replaced. Install
the newest build with `scripts/install_latest.ps1`. Target computers do not need
Python. See `docs/WINDOWS_PACKAGING.md` for prerequisites and diagnostics.

## Project structure

Processing code lives in `src/recraft/core` and `src/recraft/styles`; the
PySide6 interface lives in `src/recraft/ui`. `image_transform.py` owns the
non-destructive preparation model and renderer, while `prepared_image.py`
connects prepared canvases to preview and export style processing. Tests and
design documentation are kept in `tests` and `docs`.

## Adding a new art style

Subclass `ArtStyle`, declare metadata and parameter definitions, implement `process`, then register one instance in `create_default_registry`. No UI changes are required. See `docs/ARCHITECTURE.md`.

## Roadmap

Future work may include vector and SVG exports, procedural line and flow styles, depth maps, relief meshes, and manufacturable STL and 3MF output. See `docs/ROADMAP.md`.

## Project status

This is an early experimental prototype intended to validate the architecture and learn from generated results. APIs and output may change. ReCraft is not affiliated with HueForge or any other existing software.

## Licence

MIT. See `LICENSE`.
