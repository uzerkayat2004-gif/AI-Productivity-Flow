"""Build guards and native argv/environment checks without launching the app."""
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts import build_macos_app as builder

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def build_tree(tmp_path, monkeypatch):
    contents = tmp_path / "AI Productivity Flow.app" / "Contents"
    macos = contents / "MacOS"
    resources = contents / "Resources"
    macos.mkdir(parents=True)
    library = resources / "runtime/python/lib/libpython3.11.dylib"
    library.parent.mkdir(parents=True)
    library.write_bytes(b"test dylib")
    monkeypatch.setattr(builder, "MACOS_DIR", macos)
    monkeypatch.setattr(builder, "RESOURCES_DIR", resources)
    return contents, library


def test_native_build_rejects_nonmac_host_before_compilation(build_tree, monkeypatch):
    monkeypatch.setattr(builder.sys, "platform", "win32")
    with pytest.raises(RuntimeError, match="macOS host"):
        builder.create_native_launcher("aarch64")


def test_native_build_requires_bundled_library(build_tree, monkeypatch):
    _, library = build_tree
    library.unlink()
    monkeypatch.setattr(builder.sys, "platform", "darwin")
    monkeypatch.setattr(builder.shutil, "which", lambda name: "/usr/bin/clang")
    with pytest.raises(RuntimeError, match="libpython3.11.dylib"):
        builder.create_native_launcher("aarch64")


def test_compile_arch_and_native_replaces_shell_only_on_success(build_tree, monkeypatch):
    contents, _ = build_tree
    launcher = contents / "MacOS/ai-productivity-flow-launcher"
    launcher.write_text("#!/bin/bash\n", encoding="utf-8")
    monkeypatch.setattr(builder.sys, "platform", "darwin")
    monkeypatch.setattr(builder.shutil, "which", lambda name: "/usr/bin/clang")
    calls = []
    def compile(command, **kwargs):
        calls.append((command, kwargs))
        Path(command[-1]).write_bytes(b"\xcf\xfa\xed\xfetest")
    monkeypatch.setattr(builder.subprocess, "run", compile)
    builder.create_native_launcher("aarch64")
    command, kwargs = calls[0]
    assert command[command.index("-arch") + 1] == "arm64"
    assert "-mmacosx-version-min=12.0" in command
    assert "-framework" not in command
    assert kwargs == {"check": True}
    assert launcher.read_bytes().startswith(b"\xcf\xfa\xed\xfe")


def test_invalid_compiler_output_does_not_replace_shell(build_tree, monkeypatch):
    contents, _ = build_tree
    launcher = contents / "MacOS/ai-productivity-flow-launcher"
    original = b"#!/bin/bash\n"
    launcher.write_bytes(original)
    monkeypatch.setattr(builder.sys, "platform", "darwin")
    monkeypatch.setattr(builder.shutil, "which", lambda name: "/usr/bin/clang")
    monkeypatch.setattr(builder.subprocess, "run", lambda command, **kwargs:
                        Path(command[-1]).write_bytes(b"not a Mach-O"))
    with pytest.raises(RuntimeError, match="Mach-O"):
        builder.create_native_launcher("x86_64")
    assert launcher.read_bytes() == original


@pytest.mark.skipif(sys.platform != "darwin", reason="compiles a native stub runtime on macOS")
@pytest.mark.parametrize("arguments,expected", [
    ([], ["-m", "voice_flow.main"]),
    (["--test-crash-reporting"], ["-m", "voice_flow.main", "--test-crash-reporting"]),
    (["-m", "voice_flow.gui.desktop_launcher"], ["-m", "voice_flow.gui.desktop_launcher"]),
    (["-m", "voice_flow.audio_summary_player", "token", "depth"],
     ["-m", "voice_flow.audio_summary_player", "token", "depth"]),
    (["-c", "print(42)"], ["-c", "print(42)"]),
    (["script with spaces.py", "argument"], ["script with spaces.py", "argument"]),
])
def test_native_argv_and_bundle_paths_without_python_or_gui(tmp_path, monkeypatch, arguments, expected):
    clang = shutil.which("clang")
    assert clang, "macOS native tests require Xcode command line tools"
    contents = tmp_path / "App With Spaces.app/Contents"
    macos = contents / "MacOS"
    home = contents / "Resources/runtime/python"
    macos.mkdir(parents=True)
    (home / "lib").mkdir(parents=True)
    source = tmp_path / "stub.c"
    source.write_text(
        '#include <stdio.h>\n#include <stdlib.h>\n'
        'int Py_BytesMain(int argc, char **argv) {\n'
        ' printf("HOME=%s\\n", getenv("PYTHONHOME"));\n'
        ' printf("PATHS=%s\\n", getenv("PYTHONPATH"));\n'
        ' for(int i=0; i<argc; i++) printf("ARG=%s\\n", argv[i]);\n'
        ' return 23; }\n', encoding="utf-8")
    subprocess.run([clang, "-dynamiclib", str(source), "-o",
                    str(home / "lib/libpython3.11.dylib")], check=True)
    launcher = macos / "ai-productivity-flow-launcher"
    subprocess.run([clang, "-Wall", "-Wextra", "-Werror",
                    str(ROOT / "scripts/native_macos_launcher.c"), "-o", str(launcher)], check=True)
    monkeypatch.setenv("PYTHONHOME", "/wrong/inherited/python")
    monkeypatch.setenv("PYTHONPATH", "/preserved/custom/path")
    result = subprocess.run([str(launcher), *arguments], capture_output=True, text=True)
    assert result.returncode == 23, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == f"HOME={home}"
    assert lines[1].startswith(f"PATHS={contents}/Resources/src:")
    assert lines[1].endswith(":/preserved/custom/path")
    assert [line.removeprefix("ARG=") for line in lines[2:]] == [str(launcher), *expected]


def test_failed_compiler_preserves_existing_shell_scaffold(build_tree, monkeypatch):
    contents, _ = build_tree
    launcher = contents / "MacOS/ai-productivity-flow-launcher"
    original = b"#!/bin/bash\n# existing resource scaffold\n"
    launcher.write_bytes(original)
    monkeypatch.setattr(builder.sys, "platform", "darwin")
    monkeypatch.setattr(builder.shutil, "which", lambda name: "/usr/bin/clang")
    def fail_compile(command, **kwargs):
        # Even a partial compiler output must never replace the scaffold.
        Path(command[-1]).write_bytes(b"partial compiler output")
        raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(builder.subprocess, "run", fail_compile)
    with pytest.raises(subprocess.CalledProcessError):
        builder.create_native_launcher("aarch64")
    assert launcher.read_bytes() == original


def test_main_bundles_then_compiles_signs_and_packages_only_in_tmp(tmp_path, monkeypatch):
    # main may remove BUNDLE_DIR. Replace every builder path before calling it;
    # resource/packaging helpers are also mocked so no project output is touched.
    repo = tmp_path / "temporary repo"
    dist = repo / "dist"
    bundle = dist / "AI Productivity Flow.app"
    contents = bundle / "Contents"
    paths = {
        "REPO_ROOT": repo,
        "DIST_DIR": dist,
        "ASSETS_DIR": repo / "scripts/assets",
        "BUNDLE_DIR": bundle,
        "CONTENTS_DIR": contents,
        "MACOS_DIR": contents / "MacOS",
        "RESOURCES_DIR": contents / "Resources",
        "SRC_DIR": repo / "src/voice_flow",
    }
    for name, value in paths.items():
        assert value.resolve().is_relative_to(tmp_path.resolve())
        monkeypatch.setattr(builder, name, value)
    monkeypatch.setattr(builder.sys, "platform", "darwin")
    monkeypatch.setattr(builder.sys, "argv", ["build_macos_app.py", "--bundle-runtime", "--target-arch", "aarch64"])
    events = []
    for name in ("generate_dmg_background", "create_info_plist", "create_launcher_script",
                 "create_app_icon", "copy_resources"):
        monkeypatch.setattr(builder, name, lambda *args, **kwargs: None)
    monkeypatch.setattr(builder, "bundle_runtime_dependencies",
                        lambda **kwargs: events.append(("runtime", kwargs)))
    monkeypatch.setattr(builder, "create_native_launcher",
                        lambda **kwargs: events.append(("native", kwargs)))
    monkeypatch.setattr(builder, "sign_app_bundle",
                        lambda path: events.append(("sign", path)) or True)
    monkeypatch.setattr(builder, "package_zip", lambda: events.append(("zip", None)))
    monkeypatch.setattr(builder, "create_dmg",
                        lambda *args: events.append(("dmg", args)))
    def guarded_remove(path):
        assert Path(path).resolve().is_relative_to(tmp_path.resolve())
        raise AssertionError("A fresh temporary bundle should not need deletion")
    monkeypatch.setattr(builder.shutil, "rmtree", guarded_remove)
    builder.main()
    assert [name for name, _ in events] == ["runtime", "native", "sign", "zip", "dmg"]
    assert events[0][1] == events[1][1] == {"target_arch": "aarch64"}
    assert events[2][1] == bundle
    assert events[4][1][0] == bundle
    assert events[4][1][1] == dist / "AI-Productivity-Flow-macOS.dmg"
