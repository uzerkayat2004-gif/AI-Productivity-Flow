"""Test to ensure all public version metadata across the repository matches canonical 1.0.0."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_canonical_version_match():
    # 1. Canonical _version.py
    from voice_flow._version import VERSION
    assert VERSION == "1.0.0", f"Canonical VERSION in _version.py is {VERSION}, expected 1.0.0"

    # 2. Package __version__
    import voice_flow
    assert voice_flow.__version__ == "1.0.0", f"__version__ in __init__.py is {voice_flow.__version__}, expected 1.0.0"

    # 3. pyproject.toml
    pyproject_path = REPO_ROOT / "pyproject.toml"
    assert pyproject_path.is_file(), "pyproject.toml missing"
    content = pyproject_path.read_text(encoding="utf-8")
    m = re.search(r'version\s*=\s*"([^"]+)"', content)
    assert m, "version field not found in pyproject.toml"
    assert m.group(1) == VERSION, f"pyproject.toml version {m.group(1)} != canonical {VERSION}"

    # 4. Windows Inno Setup script
    iss_path = REPO_ROOT / "release" / "installer" / "apf-setup.iss"
    assert iss_path.is_file(), "apf-setup.iss missing"
    iss_content = iss_path.read_text(encoding="utf-8")
    m_iss = re.search(r'#define\s+MyAppVersion\s+"([^"]+)"', iss_content)
    assert m_iss, "MyAppVersion not found in apf-setup.iss"
    assert m_iss.group(1) == VERSION, f"apf-setup.iss version {m_iss.group(1)} != canonical {VERSION}"

    # 5. macOS app packaging script
    macos_builder = REPO_ROOT / "scripts" / "build_macos_app.py"
    assert macos_builder.is_file(), "build_macos_app.py missing"
    macos_content = macos_builder.read_text(encoding="utf-8")
    assert "from voice_flow._version import VERSION" in macos_content, "build_macos_app.py must import canonical VERSION"
    assert '"CFBundleShortVersionString": VERSION' in macos_content, "build_macos_app.py must use canonical VERSION for CFBundleShortVersionString"
