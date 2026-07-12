# Windows Packaging

ReCraft uses PyInstaller one-folder output and Inno Setup 6. Generated files are
replaced on every successful build and are deliberately excluded from Git.

## Prerequisites

- 64-bit Windows.
- Python 3.11 or newer for building. Target computers do not need Python.
- [Inno Setup 6](https://jrsoftware.org/isdl.php) installed in a standard
  location, available as `ISCC.exe` on `PATH`, or identified with the
  `INNO_SETUP_COMPILER` environment variable.
- Internet access for the initial dependency installation.

The project version in `pyproject.toml` is authoritative. The build script reads
installed project metadata and passes that version into Inno Setup.

## Build by double-clicking

Double-click `Build ReCraft.cmd` in the repository root. It uses a process-only
PowerShell execution-policy bypass and pauses so the result remains visible.

## Build from a terminal

From any working directory:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\path\to\ReCraft\scripts\build_release.ps1"
```

The script creates/reuses `.venv`, updates build dependencies, installs ReCraft,
runs all tests, stops on failure, safely replaces repository `build`/`dist`,
builds the windowed application, locates Inno Setup, builds the installer, checks
both outputs, and prints version, test status, paths, and sizes.

Outputs:

- `dist/ReCraft/ReCraft.exe` with its required one-folder runtime files.
- `dist/ReCraft-Setup.exe`.

## Install the latest build

Double-click the setup executable, or run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_latest.ps1
```

Installation goes to Program Files, creates a Start Menu shortcut, optionally
creates a desktop shortcut, supports normal uninstall, and can upgrade an
existing installation. Future settings belong under `%LOCALAPPDATA%\ReCraft`,
outside Program Files, and are not removed by this build workflow.

## Diagnosing packaging problems

PyInstaller warnings are written beneath `build/pyinstaller`. For missing Python
modules, reproduce the import in `.venv`, then add a precise hidden import or
official hook to `packaging/recraft.spec`. For missing resources, add a
root-relative data entry and fail the build if the source is absent. Do not
silently add broad collections without understanding their size or license.

Qt plugins are handled by PyInstaller's PySide6 hooks. OpenCV data is collected
explicitly. Rebuild after dependency upgrades and launch `dist/ReCraft/ReCraft.exe`
before distributing it. A normal packaged launch is windowed and has no console.

Never package or commit private golden test photographs. Keep private sources
and derivatives outside tracked asset directories.
