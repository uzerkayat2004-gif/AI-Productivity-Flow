from types import SimpleNamespace

from voice_flow.video_flow_models import VideoModelGateway


def test_claude_code_streams_long_prompt_over_stdin(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["input"] = kwargs.get("input")
        return SimpleNamespace(returncode=0, stdout='{"scenes": []}', stderr="")

    monkeypatch.setattr("voice_flow.video_flow_models.subprocess.run", fake_run)
    prompt = "source " * 20_000

    VideoModelGateway(None, None)._call_claude_code("sonnet", prompt)

    assert captured["input"] == prompt
    assert prompt not in captured["command"]


def test_codex_streams_long_prompt_over_stdin(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["input"] = kwargs.get("input")
        output_path = command[command.index("--output-last-message") + 1]
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write('{"scenes": []}')
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("voice_flow.video_flow_models.subprocess.run", fake_run)
    prompt = "source " * 20_000

    VideoModelGateway(None, None)._call_codex("gpt-5", prompt)

    assert captured["input"] == prompt
    assert captured["command"][-1] == "-"
    assert prompt not in captured["command"]
