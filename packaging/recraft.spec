"""PyInstaller one-folder specification for ReCraft."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

project_root = Path(SPECPATH).resolve().parent
source_root = project_root / "src"
icon_path = project_root / "src" / "recraft" / "assets" / "recraft.ico"

datas = collect_data_files("cv2")
datas += [
    (str(project_root / "src" / "recraft" / "assets" / "recraft-icon.svg"), "recraft/assets"),
]

analysis = Analysis(
    [str(source_root / "recraft" / "__main__.py")],
    pathex=[str(source_root)],
    binaries=[],
    datas=datas,
    hiddenimports=["scipy.spatial", "trimesh.exchange.stl"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="ReCraft",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(icon_path) if icon_path.exists() else None,
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ReCraft",
)
