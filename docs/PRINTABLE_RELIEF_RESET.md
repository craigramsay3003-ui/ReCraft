# Printable Relief Reset

This document describes the experimental `feature/printable-relief-reset`
branch. It does not describe stable `main`.

## Product scope

ReCraft now exposes one task: turn a photograph into a shallow positive relief
plaque. The normal workflow is Open Image, Fit/Crop, choose one preset, choose
physical size, Generate Relief, inspect, then export STL or 3MF. The source and
3D preview remain visible beside a compact control column. Advanced settings are
collapsed by default.

## Relief method

The prepared image is downsampled to a bounded analysis grid. ReCraft combines
smoothed luminance with restrained gradient and local-contrast reinforcement,
then applies generic subject/face emphasis and background suppression when the
existing analysis provides useful evidence. Percentile normalization prevents
one extreme pixel from flattening the useful range. Morphological opening
removes features below the configured physical minimum and Gaussian smoothing
removes isolated height spikes.

The normalized field drives a regular structured surface. The mesh contains a
positive front, a completely flat Z=0 rear, and closed side walls. It has no
floating path geometry or negative cavities. Preview and export share this code;
only their bounded sample counts differ.

## Presets

| Preset | Tone | Edges | Background | Physical character |
|---|---:|---:|---:|---|
| Portrait Relief | 0.62 | 0.18 | strong reduction | Continuous shallow form with extra subject and possible-face weight |
| Graphic Relief | 0.58 | 0.28 | moderate reduction | Seven cleaned poster-like height levels |
| Layered Relief | 0.78 | 0.08 | moderate/strong reduction | Five broad height bands with the strongest smoothing |

The presets are central typed data, not UI labels. Background reduction and
subject emphasis remain simple user controls. Automatic subject and face masks
are visual heuristics; ReCraft does not claim semantic scene understanding.

## Defaults and limits

- Physical width: 160 mm.
- Base: 1.5 mm.
- Relief above base: 1.8 mm.
- Minimum feature: 0.8 mm.
- Test profile: Bambu H2C with selected 0.4 mm nozzle and 0.2 mm layer height.
- Preview maximum: 150,000 triangles.
- Export maximum: 350,000 triangles.
- Preview quality: 150 samples on the longest image dimension.
- Fine export quality: 260 samples on the longest image dimension.

Validation rejects unsafe dimensions, undersized nozzle features, relief depth
below three selected layers, non-finite height data, triangle-budget overruns,
and non-watertight geometry.

## Viewer and generation states

Use left-drag to orbit, middle-drag or Shift-drag to pan, and the wheel to zoom.
Fit, Reset, Front, Perspective, and Orthographic are always close to the mesh.
Camera changes operate only on compact copied render buffers.

The interface explicitly shows Open an image, Settings changed — regenerate,
Generating with a named stage, Preview up to date, or Generation failed. The
previous valid mesh is retained while a replacement is built or if it fails.

## Export

STL is one watertight millimetre-scale geometry-only plaque. STL cannot preserve
colour. 3MF contains the same single reliable object, millimetre units, correct
orientation, and a display material. Separate multicolour base/relief objects
were deliberately deferred so they cannot jeopardize the first print.

Always inspect and slice the generated STL in Bambu Studio before printing. The
repository uses synthetic images for tests. The private golden family image may
be used locally only and must not be committed, packaged, logged by filename,
used as a fixture, or captured in public screenshots.

## Local test

```powershell
git switch feature/printable-relief-reset
git pull
.\.venv\Scripts\python.exe -m pip install -e ".[dev,build]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m recraft
```

If PowerShell script activation is blocked, these commands intentionally invoke
the virtual-environment Python directly and require no activation-policy change.
