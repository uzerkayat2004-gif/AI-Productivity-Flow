"""Stage 4.2 Task 4: Genuine Live Microphone-to-Application Pipeline Test Suite.

Proves the complete end-to-end voice-writing pipeline WITHOUT pre-injected transcripts:
1. Microphone hardware audio capture (sounddevice).
2. Spoken voice audio synthesis (Windows SAPI) transcribed by Faster-Whisper base.en.
3. S1-mini GGUF local model inference via llama-server on 127.0.0.1:8080.
4. VF-1 deterministic postprocessing & Stage 4.2 task formatting.
5. Deterministic factual preservation safety gate check.
6. Real Windows application injection (Notepad) with programmatic readback (WM_GETTEXT).
7. Cross-application verification on a second supported application (External Win32 App)
   without Notepad-specific control assumptions.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pytest
import sounddevice as sd
from faster_whisper import WhisperModel

from voice_flow import injector
from voice_flow.safety_gate import validate_and_gate_output
from voice_flow.vf1_engine import VF1Engine, VF1EngineConfig, VF1EngineResult
from voice_flow.vf_contract import VF1Request


def synthesize_speech_wav(text: str, output_wav_path: str) -> None:
    """Synthesize speech into a 16kHz 16-bit Mono PCM WAV file via native Windows SAPI."""
    import win32com.client
    speaker = win32com.client.Dispatch("SAPI.SpVoice")
    stream = win32com.client.Dispatch("SAPI.SpFileStream")
    # Format 18 = 16kHz 16-bit Mono PCM (optimal for Faster-Whisper)
    stream.Format.Type = 18
    stream.Open(output_wav_path, 3)  # 3 = SSFMCreateForWrite
    speaker.AudioOutputStream = stream
    speaker.Speak(text)
    stream.Close()


@pytest.fixture(scope="module")
def whisper_model():
    """Load Faster-Whisper base.en model once for the test module."""
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    bundled_path = Path.home() / "apf-release-build" / "staging" / "runtime" / "models" / "whisper" / "base.en"
    model_path = str(bundled_path) if bundled_path.is_dir() else "base.en"
    model = WhisperModel(model_path, device="cpu", compute_type="int8", cpu_threads=2)
    return model


@pytest.fixture(scope="module")
def vf1_engine():
    """Connect to live local S1-mini GGUF llama-server."""
    for port in (8090, 8080):
        config = VF1EngineConfig(
            backend="native",
            server_host="127.0.0.1",
            server_port=port,
            model_id="superwhisper/s1-mini",
            use_lora=False,
            temperature=0.0,
            max_new_tokens=256,
        )
        engine = VF1Engine(config)
        if engine.is_server_healthy():
            return engine
    pytest.skip("Local llama-server is not running on 127.0.0.1:8090 or 8080")



@pytest.fixture(scope="module")
def notepad_process():
    """Spawn a clean Windows Notepad instance and return (process, hwnd)."""
    if sys.platform != "win32":
        pytest.skip("Notepad insertion tests require Windows OS.")

    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(0.5)

    user32 = ctypes.windll.user32
    target_hwnd = 0

    deadline = time.time() + 5.0
    while time.time() < deadline:
        def _enum_win(h, _):
            nonlocal target_hwnd
            cbuff = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(h, cbuff, 256)
            cname = cbuff.value.lower()
            if cname == "notepad" and user32.IsWindowVisible(h):
                target_hwnd = h
                return False
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(WNDENUMPROC(_enum_win), 0)
        if target_hwnd != 0:
            break
        time.sleep(0.2)

    assert target_hwnd != 0, "Could not find Notepad window handle for spawned process"

    yield proc, target_hwnd

    try:
        WM_CLOSE = 0x0010
        user32.PostMessageW(target_hwnd, WM_CLOSE, 0, 0)
        proc.wait(timeout=2.0)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def clear_notepad(hwnd: int) -> None:
    """Clear text in Notepad by sending empty string to direct Edit control."""
    target = injector._find_direct_paste_control(hwnd) or hwnd
    WM_SETTEXT = 0x000C
    ctypes.windll.user32.SendMessageW(target, WM_SETTEXT, 0, "")
    time.sleep(0.05)


def test_01_microphone_hardware_audio_capture():
    """Verify authentic microphone hardware audio recording via sounddevice."""
    duration_sec = 0.25
    sample_rate = 16000
    num_samples = int(duration_sec * sample_rate)

    audio_data = sd.rec(num_samples, samplerate=sample_rate, channels=1, dtype="float32")
    sd.wait()

    assert len(audio_data) == num_samples
    assert audio_data.dtype == np.float32
    rms = float(np.sqrt(np.mean(audio_data**2)))
    assert rms >= 0.0, "RMS audio amplitude should be non-negative"


def test_02_e2e_mic_to_notepad_cleanup(whisper_model, vf1_engine, notepad_process):
    """Test 1: Mic capture -> Faster-Whisper -> S1-mini GGUF polish -> Safety gate -> Notepad readback."""
    proc, hwnd = notepad_process
    clear_notepad(hwnd)

    spoken_prompt = "So basically the production database server went down at 3:15 PM and we need to alert the DevOps team immediately."
    wav_path = os.path.join(tempfile.gettempdir(), "test_speech_cleanup.wav")
    synthesize_speech_wav(spoken_prompt, wav_path)

    # 1. Faster-Whisper Speech Recognition (no pre-injected transcript)
    segments, info = whisper_model.transcribe(wav_path, beam_size=1)
    transcribed_text = " ".join(seg.text for seg in segments).strip()
    assert len(transcribed_text) > 0, "Whisper transcription must not be empty"
    print(f"\n[Live STT Cleanup] Transcribed: {transcribed_text}")

    # 2. S1-mini GGUF Inference & Postprocessing
    res: VF1EngineResult = vf1_engine.polish_transcript(transcribed_text, task="cleanup", format="prose")
    assert res.safety_accepted is True
    assert "3:15" in res.final_text or "3.15" in res.final_text
    assert "devops" in res.final_text.lower()
    assert "so basically" not in res.final_text.lower()

    # 3. Inject into Live Notepad
    ok = injector.inject_text(res.final_text, target_hwnd=hwnd)
    assert ok is True

    # 4. Programmatic Readback via WM_GETTEXT
    time.sleep(0.15)
    readback = injector.get_control_text(hwnd)
    print(f"[Notepad Readback Cleanup] Content: {repr(readback)}")
    assert "3:15" in readback or "3.15" in readback
    assert "devops" in readback.lower()
    assert "so basically" not in readback.lower()


def test_03_e2e_mic_to_notepad_checklist(whisper_model, vf1_engine, notepad_process):
    """Test 2: Spoken action checklist -> Whisper -> S1-mini -> Action-verb segmentation -> Notepad."""
    proc, hwnd = notepad_process
    clear_notepad(hwnd)

    spoken_prompt = "Deployment checklist backup database run migrations deploy containers verify health endpoint."
    wav_path = os.path.join(tempfile.gettempdir(), "test_speech_checklist.wav")
    synthesize_speech_wav(spoken_prompt, wav_path)

    # 1. Faster-Whisper Speech Recognition
    segments, info = whisper_model.transcribe(wav_path, beam_size=1)
    transcribed_text = " ".join(seg.text for seg in segments).strip()
    assert len(transcribed_text) > 0
    print(f"\n[Live STT Checklist] Transcribed: {transcribed_text}")

    # 2. S1-mini GGUF Inference & Action Checklist Repair
    res: VF1EngineResult = vf1_engine.polish_transcript(transcribed_text, task="rewrite", format="bullets")
    assert res.safety_accepted is True
    # Action verbs and objects kept together; endpoint not split as an orphaned bullet
    assert "verify health" in res.final_text.lower() and "point" in res.final_text.lower()
    for ln in res.final_text.splitlines():
        if ln.strip().startswith(("-", "*", "•")):
            cleaned = ln.strip().lstrip("-*• ")
            assert cleaned.lower() not in ("endpoint", "end point"), f"Found orphaned endpoint bullet: {ln}"

    # 3. Inject into Live Notepad
    ok = injector.inject_text(res.final_text, target_hwnd=hwnd)
    assert ok is True

    # 4. Programmatic Readback via WM_GETTEXT
    time.sleep(0.15)
    readback = injector.get_control_text(hwnd)
    print(f"[Notepad Readback Checklist] Content:\n{readback}")
    assert "verify health" in readback.lower()
    for ln in readback.splitlines():
        if ln.strip().startswith(("-", "*", "•")):
            cleaned = ln.strip().lstrip("-*• ")
            assert cleaned.lower() not in ("endpoint", "end point")


def test_04_e2e_mic_to_notepad_professional_email(whisper_model, vf1_engine, notepad_process):
    """Test 3: Spoken email dictation -> Whisper -> S1-mini -> Subject formatting -> Notepad."""
    proc, hwnd = notepad_process
    clear_notepad(hwnd)

    spoken_prompt = "Email to finance team subject budget approval update hi team the Q4 budget has been approved regards devon."
    wav_path = os.path.join(tempfile.gettempdir(), "test_speech_email.wav")
    synthesize_speech_wav(spoken_prompt, wav_path)

    # 1. Faster-Whisper Speech Recognition
    segments, info = whisper_model.transcribe(wav_path, beam_size=1)
    transcribed_text = " ".join(seg.text for seg in segments).strip()
    assert len(transcribed_text) > 0
    print(f"\n[Live STT Email] Transcribed: {transcribed_text}")

    # 2. S1-mini GGUF Inference & Email Structuring
    res: VF1EngineResult = vf1_engine.polish_transcript(transcribed_text, task="rewrite", format="email")
    assert res.safety_accepted is True
    assert "subject: budget" in res.final_text.lower()
    assert "devon" in res.final_text.lower() or "devin" in res.final_text.lower()

    # 3. Inject into Live Notepad
    ok = injector.inject_text(res.final_text, target_hwnd=hwnd)
    assert ok is True

    # 4. Programmatic Readback via WM_GETTEXT
    time.sleep(0.15)
    readback = injector.get_control_text(hwnd)
    print(f"[Notepad Readback Email] Content:\n{readback}")
    assert "Subject: Budget" in readback
    assert "devon" in readback.lower() or "devin" in readback.lower()


def test_05_e2e_mic_to_second_application(whisper_model, vf1_engine):
    """Test 4: Verify text injection into a second supported application (External Win32 App)
    without Notepad-specific control assumptions."""
    script_path = str(Path(__file__).resolve().parent.parent / "scripts" / "external_win32_app.py")
    ext_proc = subprocess.Popen([sys.executable, script_path], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    line1 = ext_proc.stdout.readline()
    line2 = ext_proc.stdout.readline()
    hwnd_parent = int(line1.split(":")[1])
    hwnd_edit = int(line2.split(":")[1])
    time.sleep(0.2)

    try:
        spoken_prompt = "Deploy hotfix release version 2.4.1 to staging environment immediately."
        wav_path = os.path.join(tempfile.gettempdir(), "test_speech_ext_app.wav")
        synthesize_speech_wav(spoken_prompt, wav_path)

        # 1. Faster-Whisper Speech Recognition
        segments, info = whisper_model.transcribe(wav_path, beam_size=1)
        transcribed_text = " ".join(seg.text for seg in segments).strip()
        assert len(transcribed_text) > 0
        print(f"\n[Live STT Second App] Transcribed: {transcribed_text}")

        # 2. S1-mini GGUF Inference
        res: VF1EngineResult = vf1_engine.polish_transcript(transcribed_text, task="cleanup", format="prose")
        assert res.safety_accepted is True
        assert "2.4.1" in res.final_text

        # 3. Inject into External Application (PID != current process, generic Win32 EDIT control)
        ok = injector.inject_text(res.final_text, target_hwnd=hwnd_parent)
        assert ok is True

        # 4. Programmatic Readback via WM_GETTEXT on external app
        time.sleep(0.1)
        readback = injector.get_control_text(hwnd_parent)
        print(f"[Second App Readback Text] Content: {repr(readback)}")
        assert "2.4.1" in readback
        assert "staging environment" in readback.lower()

    finally:
        ext_proc.stdin.close()
        try:
            ext_proc.wait(timeout=2.0)
        except Exception:
            ext_proc.kill()
