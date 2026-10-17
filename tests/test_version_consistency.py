"""Internal build and user-facing version stay in one place and do not drift."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_canonical_version_match():
    # 1. Canonical _version.py
    from voice_flow._version import DISPLAY_VERSION, VERSION
    assert VERSION == "1.0.6", f"Canonical VERSION in _version.py is {VERSION}, expected 1.0.6"
    assert DISPLAY_VERSION == "1.0", f"DISPLAY_VERSION is {DISPLAY_VERSION}, expected 1.0"
    assert DISPLAY_VERSION != VERSION

    # 2. Package __version__
    import voice_flow
    assert voice_flow.__version__ == "1.0.6", f"__version__ in __init__.py is {voice_flow.__version__}, expected 1.0.6"

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
    m_display = re.search(r'#define\s+MyAppDisplayVersion\s+"([^"]+)"', iss_content)
    assert m_display, "MyAppDisplayVersion not found in apf-setup.iss"
    assert m_display.group(1) == DISPLAY_VERSION
    assert "AppVerName={#MyAppName} {#MyAppDisplayVersion}" in iss_content
    assert "AppVersion={#MyAppVersion}" in iss_content
    assert "VersionInfoProductTextVersion={#MyAppVersion}" in iss_content
    assert "VersionInfoVersion={#MyAppVersion}.0" in iss_content

    # 5. macOS app packaging script
    macos_builder = REPO_ROOT / "scripts" / "build_macos_app.py"
    assert macos_builder.is_file(), "build_macos_app.py missing"
    macos_content = macos_builder.read_text(encoding="utf-8")
    assert "from voice_flow._version import DISPLAY_VERSION, VERSION" in macos_content
    assert '"CFBundleShortVersionString": DISPLAY_VERSION' in macos_content
    assert '"CFBundleVersion": VERSION' in macos_content

    # 6. User-facing copy uses the display version. The About build id is the
    #    only place a 1.0.x string is allowed on screen.
    html = (REPO_ROOT / "src" / "voice_flow" / "gui" / "index.html").read_text(encoding="utf-8")
    assert f"Version {DISPLAY_VERSION}" in html
    assert f"build {VERSION}" in html
    assert "Version 1.0.6" not in html
    script = (REPO_ROOT / "src" / "voice_flow" / "gui" / "app.js").read_text(encoding="utf-8")
    assert "display_version" in script
    assert "Version ${data.current_version}" not in script
    assert "v${data.latest_version" not in script
    assert "v${data.current_version" not in script
    release = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "DISPLAY_VERSION" in release
    assert 'AI Productivity Flow $display' in release
    assert 'AI Productivity Flow $tag' not in release
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "Release-Version%201.0" in readme
    assert "v1.0.3" not in readme
    facts = (REPO_ROOT / "docs" / "PRODUCT_FACTS.md").read_text(encoding="utf-8")
    assert "Public version**: 1.0" in facts
    assert "Internal build**: 1.0.6" in facts
