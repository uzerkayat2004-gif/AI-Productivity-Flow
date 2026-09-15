"""Static contracts for the Voice Flow-only desktop pages."""
from pathlib import Path
import json
import subprocess


ROOT = Path(__file__).parents[1]
GUI = ROOT / "src" / "voice_flow" / "gui"


def test_polish_speed_loader_is_not_gated_by_provider_overview() -> None:
    js = (GUI / "app.js").read_text(encoding="utf-8")
    overview = js.split("async function loadProvidersOverview()", 1)[1].split(
        "// Voice Flow polishing-policy model picker state", 1
    )[0]

    assert overview.index("loadVoiceFlowPolishSettings();") < overview.index("try {")


def test_style_ui_exposes_the_persisted_developer_category() -> None:
    html = (GUI / "index.html").read_text(encoding="utf-8")
    js = (GUI / "app.js").read_text(encoding="utf-8")
    style_page = html[html.index('id="page-style"'):html.index('id="page-providers"')]
    style_data = js[js.index("const STYLE_DATA"):js.index("let currentStyleCategory")]
    selected_start = js.index("let selectedStyles")
    selected = js[selected_start:js.index("\n};", selected_start) + 3]

    assert "switchStyleTab('developer', this)" in style_page
    assert "developer: {" in style_data
    assert 'developer: "developer_casual"' in selected
    for preset in (
        "developer_formal",
        "developer_casual",
        "developer_very_casual",
        "developer_excited",
    ):
        assert preset in style_data


def test_voice_flow_stt_and_polish_pickers_keep_separate_catalogues_and_routes() -> None:
    """The shared modal must not turn the STT button into the polish picker."""
    app = (GUI / "app.js").read_text(encoding="utf-8")
    picker = (GUI / "video-flow.js").read_text(encoding="utf-8")

    stt_opener = app[
        app.index("async function openVoiceFlowModelPicker()"):
        app.index("async function loadExecVoiceFlowPolicy()")
    ]
    polish_opener = app[
        app.index("async function openVoiceFlowPolishModelPicker()"):
        app.index("async function saveVoiceFlowPolishModel(modelRef)")
    ]
    chooser = picker[
        picker.index("function chooseVideoModel(modelRef)"):
        picker.index("function toggleVideoHistory()")
    ]

    assert "await loadExecVoiceFlowPolicy();" in stt_opener
    assert 'openVideoModelPicker("voice_flow_stt")' in stt_opener
    assert 'openVideoModelPicker("voice_flow")' not in stt_opener
    assert "await loadVoiceFlowPolishSettings();" in polish_opener
    assert 'openVideoModelPicker("voice_flow_polish")' in polish_opener
    assert 'vfModelPickerContext === "voice_flow_stt"' in picker
    assert 'vfModelPickerContext === "voice_flow_polish"' in picker
    assert "Select the speech-to-text model" in picker
    assert "Select the polishing model" in picker
    assert 'updateExecVoiceFlowPolicy(modelRef);' in chooser
    assert 'saveVoiceFlowPolishModel(modelRef);' in chooser


def test_voice_flow_model_save_failures_reload_the_persisted_selection() -> None:
    """A failed picker save must restore the server's previously saved model."""
    app = (GUI / "app.js").read_text(encoding="utf-8")
    stt_saver = app[
        app.index("async function updateExecVoiceFlowPolicy(modelVal)"):
        app.index("function filterProvidersList()")
    ]
    polish_saver = app[
        app.index("async function saveVoiceFlowPolishModel(modelRef)"):
        app.index("// =========================================================================", app.index("async function saveVoiceFlowPolishModel(modelRef)"))
    ]

    assert 'fetch("/api/voice-flow-stt/update"' in stt_saver
    assert "await loadExecVoiceFlowPolicy();" in stt_saver
    assert 'fetch("/api/voice-flow-polish/update"' in polish_saver
    assert polish_saver.index("voiceFlowPolishModelRef = data.active_model || modelRef;") < polish_saver.index("} catch (error) {")
    assert "loadVoiceFlowPolishSettings();" in polish_saver.split("} catch (error) {", 1)[1]


def test_shared_renderer_uses_each_voice_policy_catalogue() -> None:
    """Policy-only Polish models must never be replaced by the STT catalogue."""
    harness = r'''
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync(process.argv[1], "utf8");
const start = source.indexOf("function vfSelectableVideoModels()");
const end = source.indexOf("let vfModelPickerContext", start);
const root = { innerHTML: "" };
const context = {
  console, Set, Map,
  vfCatalog: { models: [] }, vfProviderIcons: {},
  vfEscape: value => String(value ?? ""),
  vfJsArg: value => JSON.stringify(value),
  vfCapabilityBadges: () => "",
  document: { getElementById: id => id === "vf-model-picker-list" ? root : id === "vf-model-picker-search" ? { value: "" } : null },
  voiceFlowPolicyModelRef: "stt/only-model",
  voiceFlowPolishModelRef: "polish/only-model",
  voiceFlowPolicyModels: [{ full_id: "stt/only-model", display_name: "STT only", provider: "stt", provider_name: "STT", capabilities: [] }],
  voiceFlowPolishModels: [{ full_id: "polish/only-model", label: "Polish only", display_name: "Polish only", provider: "polish", provider_name: "Polish", capabilities: [] }],
};
vm.runInNewContext(source.slice(start, end), context);
context.vfModelPickerContext = "voice_flow_stt";
context.vfPickerAllowedRefs = new Set(["stt/only-model"]);
context.renderVideoModelPicker();
const stt = root.innerHTML;
context.vfModelPickerContext = "voice_flow_polish";
context.vfPickerAllowedRefs = new Set(["polish/only-model"]);
context.renderVideoModelPicker();
process.stdout.write(JSON.stringify({ stt, polish: root.innerHTML }));
'''
    result = subprocess.run(
        ["node", "-e", harness, str(GUI / "video-flow.js")],
        check=True,
        capture_output=True,
        text=True,
    )
    rendered = json.loads(result.stdout)

    assert "STT only" in rendered["stt"]
    assert "Polish only" not in rendered["stt"]
    assert "Polish only" in rendered["polish"]
    assert "STT only" not in rendered["polish"]
