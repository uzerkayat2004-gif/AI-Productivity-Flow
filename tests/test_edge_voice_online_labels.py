"""B6: Edge TTS voices send text to Microsoft and must be labelled as online in the UI."""

from __future__ import annotations

from pathlib import Path

from voice_flow.storage import storage

GUI = Path(__file__).resolve().parents[1] / "src" / "voice_flow" / "gui"


def test_seeded_edge_voices_are_labelled_online():
    with storage._get_conn() as conn:
        rows = conn.execute("SELECT display_name FROM tts_models WHERE provider = 'edge'").fetchall()
    names = [r["display_name"] for r in rows]
    assert names, "edge voices should be seeded"
    assert all("Online" in n for n in names), names


def test_edge_provider_name_in_audio_policy_is_online():
    policy = storage.get_exec_audio_policy_options()
    edge_groups = [g for g in policy.get("grouped_models") or [] if g.get("provider") == "edge"]
    assert edge_groups
    assert all(g["provider_name"] == "Microsoft Edge Neural (Online)" for g in edge_groups)
    assert policy["active_model"].startswith("edge/")  # default stays Edge, but labelled


def test_ui_labels_and_privacy_hint():
    app = (GUI / "app.js").read_text(encoding="utf-8")
    html = (GUI / "index.html").read_text(encoding="utf-8")
    vf = (GUI / "video-flow.js").read_text(encoding="utf-8")
    assert "Microsoft Edge Neural (Online)" in app
    assert '"Microsoft Edge Neural"' not in app
    assert "text-to-speech service" in app
    assert 'updateOnlineVoiceHint("exec-audio-online-hint", activeModel)' in app
    assert 'id="exec-audio-online-hint"' in html and 'id="vf-online-voice-hint"' in html
    assert "Microsoft Edge Ava (Online)" in html
    assert "Edge Ava (Calm Female)" not in html
    assert '"Edge TTS (free)"' not in vf and "Edge TTS (online, free)" in vf
    assert 'updateOnlineVoiceHint("vf-online-voice-hint"' in vf
