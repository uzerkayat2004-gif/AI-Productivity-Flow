from __future__ import annotations

from pathlib import Path
import voice_flow.video_flow_widget as widget_module


def test_native_composer_uses_compact_model_label_and_scoped_orange_theme() -> None:
    source = Path(widget_module.__file__).read_text(encoding="utf-8")
    assert 'self._label(model_cell, "Model provider · model")' in source
    assert 'self._label(shell, "Planning model")' not in source
    assert '"background": "#fff8f3"' in source
    assert '"orange": "#ff6b19"' in source


def test_native_composer_has_a_compact_single_row_source_toolbar() -> None:
    source = Path(widget_module.__file__).read_text(encoding="utf-8")

    assert 'win.geometry("560x600")' in source
    assert 'model_cell.grid(row=0, column=0' in source
    assert 'theme_cell.grid(row=0, column=1' in source
    assert 'self._label(shell, "Your visual direction (optional)")' in source
    assert '"visual_direction": visual_direction' in source
    assert '"visual_direction": self._controls["visual_direction"].get("1.0", "end-1c").strip()[:1000]' in source


def test_native_composer_model_options_match_in_app_availability() -> None:
    catalog = {
        "models": [
            {"full_id": "local/deterministic", "available": True, "is_active": True},
            {
                "full_id": "openai/gpt-4.1",
                "provider_name": "OpenAI",
                "display_name": "GPT-4.1",
                "available": True,
                "is_active": True,
                "capabilities": ["reasoning"],
            },
            {"full_id": "gemini/offline", "available": False, "is_active": True},
            {"full_id": "groq/disabled", "available": True, "is_active": False},
        ],
        "combos": [
            {
                "name": "Reliable route",
                "ref": "combo:Reliable route",
                "models": ["local/deterministic", "openai/gpt-4.1"],
                "strategy": "fallback",
            },
            {"name": "Unavailable", "models": ["gemini/offline"]},
        ],
    }

    options = widget_module.VideoFlowScreenWidget.catalog_model_options(catalog)

    assert [option["ref"] for option in options] == [
        "openai/gpt-4.1",
    ]
    assert options[-1]["label"] == "OpenAI · GPT-4.1"
    assert "openai/gpt-4.1" in options[-1]["detail"]


def test_native_composer_themes_keep_a_labeled_auto_option() -> None:
    options = widget_module.VideoFlowScreenWidget.catalog_theme_options(
        {"themes": ["auto", "voice-flow", "sunset", "voice-flow"]}
    )

    assert [(option["ref"], option["label"]) for option in options] == [
        ("auto", "Auto"),
        ("voice-flow", "Voice Flow"),
        ("sunset", "Sunset"),
    ]


def test_public_native_composer_launcher_routes_to_shared_widget(monkeypatch) -> None:
    class Composer:
        def __init__(self) -> None:
            self.root = None
            self.callback = None
            self.launch_args = None

        def attach_root(self, root) -> None:
            self.root = root

        def launch(self, selected_text: str, mode: str):
            self.launch_args = (selected_text, mode)
            return self

    composer = Composer()
    callback = lambda payload: {"id": "video-1"}
    monkeypatch.setattr(widget_module, "video_flow_widget", composer)

    result = widget_module.launch_video_flow_composer(
        "Selected source", "full", root="overlay-root", on_generate=callback
    )

    assert result is composer
    assert composer.root == "overlay-root"
    assert composer.callback is None
    assert composer.on_generate is callback
    assert composer.launch_args == ("Selected source", "full")
