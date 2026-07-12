from pathlib import Path
import tomllib

from recraft import __version__


ROOT = Path(__file__).parents[1]


def test_project_metadata_is_authoritative_version() -> None:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        configured = tomllib.load(stream)["project"]["version"]
    assert __version__ == configured


def test_packaging_sources_and_assets_are_checked_in() -> None:
    required = (
        "scripts/build_release.ps1", "scripts/install_latest.ps1",
        "packaging/recraft.spec", "packaging/installer.iss",
        "src/recraft/assets/recraft.ico", "src/recraft/assets/recraft-icon.svg",
        "Build ReCraft.cmd",
    )
    for relative in required:
        assert (ROOT / relative).is_file(), f"Missing packaging input: {relative}"


def test_installer_version_is_injected_not_duplicated() -> None:
    definition = (ROOT / "packaging/installer.iss").read_text(encoding="utf-8")
    assert "#ifndef AppVersion" in definition
    assert "AppVersion={#AppVersion}" in definition
    assert 'AppVersion="0.1.0"' not in definition
