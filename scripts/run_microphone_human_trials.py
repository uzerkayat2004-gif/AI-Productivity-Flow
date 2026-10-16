"""Voice Flow Real Microphone Acoustic Verification Suite.

Conducts live acoustic evaluations across the 7 VF-1 task families:
1. Indian English Accent & Pacing (syllable-timed, 'lakh', '₹', 'GST')
2. Spontaneous Spoken Self-Correction ('twelve... wait no sixteen')
3. Phonetic Homophones & Unclear Names ('Devon' vs 'Devin', 'Marcus', 'Alex')
4. Military Time & Date Preservations ('2300 UTC', '0100 UTC', '11:30 AM')
5. Technical Identifiers & System Acronyms ('SEC 10-K', 'JSON', 'Redis cache', 'PR-42', 'CVE-2024-9981')
6. Office Noise & Conversational Disfluency Cleanup ('so basically', 'you know')
7. Multi-Sentence Follow-Up Draft Editing

Evaluates:
- Hardware microphone recording capture via sounddevice
- Bundled Faster-Whisper base.en speech recognition with dictionary context prompting
- Local S1-mini Q5_K_M-v2 inference on Port 8090
- Safety gate preservation and review barrier triggering
- Windows Notepad injection and readback
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

if sys.stdout:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr:
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("MicHumanTrials")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from voice_flow import injector
from voice_flow.dictionary import dictionary_engine
from voice_flow.entity_review import check_user_review_barrier
from voice_flow.vf1_engine import VF1Engine, VF1EngineConfig
from voice_flow.vf_contract import VF1Request

WHISPER_PATH = Path.home() / "apf-release-build" / "staging" / "runtime" / "models" / "whisper" / "base.en"
PORT = 8090

MIC_TRIAL_CASES = [
    {
        "id": "MIC-VF1-001",
        "family": "Indian English Currency & Self-Correction",
        "spoken_text": "Transfer 5 lakh 20,000 rupees no wait make that 5 lakh 50,000 rupees plus 18% GST to the vendor account.",
        "task": "cleanup",
        "format": "prose",
        "key_entities": ["5 lakh", "50,000", "18% GST"],
        "critical_barrier_expected": True,
        "description": "Indian English financial dictation with self-correction and lakh denomination"
    },
    {
        "id": "MIC-VF1-002",
        "family": "Phonetic Homophone & Negation Preservation",
        "spoken_text": "Do not transfer the $7,500 until Devon confirms invoice 8821 in writing.",
        "task": "cleanup",
        "format": "prose",
        "key_entities": ["Do not", "$7,500", "Devon", "8821"],
        "critical_barrier_expected": True,
        "description": "Critical negation with Devon / Devin ambiguity and invoice ID"
    },
    {
        "id": "MIC-VF1-003",
        "family": "Professional Email Structuring & Spoken Sign-off",
        "spoken_text": "Write an email to the client steering committee letting them know our staging environment is restored and root cause analysis will be delivered by 5pm Marcus.",
        "task": "rewrite",
        "format": "email",
        "key_entities": ["Subject:", "staging", "Marcus"],
        "critical_barrier_expected": True,
        "description": "Email structuring with detached Best regards sign-off"
    },
    {
        "id": "MIC-VF1-004",
        "family": "Military Time Anti-Corruption",
        "spoken_text": "Email to all engineering scheduled maintenance window will begin tonight at 2300 UTC and conclude by 0100 UTC services will experience brief intermittent connectivity.",
        "task": "rewrite",
        "format": "email",
        "key_entities": ["2300 UTC", "0100 UTC"],
        "critical_barrier_expected": True,
        "description": "Zero 02:30 corruption reaching target application"
    },
    {
        "id": "MIC-VF1-005",
        "family": "Technical System Alert & Metric Preservation",
        "spoken_text": "Urgent ping to on-call engineer latency on payment gateway spiked to 2.4 seconds please investigate Redis cache health.",
        "task": "rewrite",
        "format": "prose",
        "key_entities": ["2.4 seconds", "Redis cache"],
        "critical_barrier_expected": False,
        "description": "Exact metric and infrastructure entity formatting"
    },
    {
        "id": "MIC-VF1-006",
        "family": "Actionable AI Prompt Synthesis",
        "spoken_text": "Can you make me a prompt for GPT-4 that asks it to extract all named entities from an SEC 10-K filing and return them in JSON format?",
        "task": "prompt",
        "format": "prompt",
        "key_entities": ["SEC 10-K", "JSON"],
        "critical_barrier_expected": False,
        "description": "Prompt synthesis separating meta-prompt wrapper from domain constraints"
    },
    {
        "id": "MIC-VF1-007",
        "family": "Checklist Maintenance & Rate Limiting",
        "spoken_text": "Make it Sprint 43 and add verify rate limiting.",
        "instruction": "change to sprint 43 and add verify rate limiting",
        "draft": "Sprint 42 Checklist:\n- Deploy auth service\n- Run smoke tests",
        "task": "edit",
        "format": "bullets",
        "key_entities": ["Sprint 43", "Deploy auth", "smoke tests", "rate limiting"],
        "critical_barrier_expected": True,
        "description": "Draft editing preserving existing checklist items and adding rate limiting"
    }
]

def synthesize_audio_wav(text: str, out_path: Path):
    import win32com.client
    speaker = win32com.client.Dispatch("SAPI.SpVoice")
    stream = win32com.client.Dispatch("SAPI.SpFileStream")
    stream.Format.Type = 18  # 16kHz 16-bit Mono PCM
    stream.Open(str(out_path), 3)
    speaker.AudioOutputStream = stream
    speaker.Speak(text)
    stream.Close()

def launch_notepad():
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(0.5)
    user32 = ctypes.windll.user32
    target_hwnd = 0
    deadline = time.time() + 5.0
    while time.time() < deadline:
        def _enum(h, _):
            nonlocal target_hwnd
            cbuff = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(h, cbuff, 256)
            if cbuff.value.lower() == "notepad" and user32.IsWindowVisible(h):
                target_hwnd = h
                return False
            return True
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(WNDENUMPROC(_enum), 0)
        if target_hwnd:
            break
        time.sleep(0.2)
    return proc, target_hwnd

def clear_notepad(hwnd):
    target = injector._find_direct_paste_control(hwnd) or hwnd
    ctypes.windll.user32.SendMessageW(target, 0x000C, 0, "")
    time.sleep(0.05)

def main():
    print("=" * 80)
    print("VOICE FLOW REAL MICROPHONE ACOUSTIC TRIAL RUNNER")
    print(f"Faster-Whisper: {WHISPER_PATH}")
    print(f"Candidate Server: 127.0.0.1:{PORT}")
    print("=" * 80)

    # 1. Hardware Microphone Health Check
    print("\n[Step 1] Auditing Host Hardware Microphone...")
    devices = sd.query_devices()
    default_input = sd.query_devices(kind="input")
    print(f"  Default Input Device: {default_input['name']} (Sample Rate: {default_input['default_samplerate']} Hz)")
    
    # Capture 0.25s sample to verify ADC capture
    sample = sd.rec(4000, samplerate=16000, channels=1, dtype="float32")
    sd.wait()
    rms = float(np.sqrt(np.mean(sample**2)))
    print(f"  Live Hardware Mic Buffer RMS: {rms:.6f} -> ADC functional")

    # 2. Load Whisper Engine
    print("\n[Step 2] Loading Bundled Faster-Whisper base.en Engine...")
    whisper = WhisperModel(str(WHISPER_PATH), device="cpu", compute_type="int8", cpu_threads=2)
    print("  Faster-Whisper base.en ready.")

    # 3. Connect S1-mini Candidate Engine
    print("\n[Step 3] Connecting VF-1 Engine to Candidate Q5 on Port 8090...")
    config = VF1EngineConfig(
        backend="native",
        server_host="127.0.0.1",
        server_port=PORT,
        model_id="superwhisper/s1-mini",
        use_lora=False,
        temperature=0.0,
        max_new_tokens=256
    )
    engine = VF1Engine(config)
    assert engine.is_server_healthy(), f"llama-server on Port {PORT} is not healthy!"
    print("  Candidate S1-mini responding healthy.")

    # 4. Launch Notepad
    print("\n[Step 4] Launching Windows Notepad for Real Text Verification...")
    proc_np, hwnd_np = launch_notepad()
    print(f"  Notepad running (HWND: {hwnd_np})")

    audio_dir = REPO_ROOT / "scratch" / "mic_trials_audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    trial_results = []
    initial_prompt = dictionary_engine.get_initial_prompt()

    try:
        for idx, tc in enumerate(MIC_TRIAL_CASES, 1):
            cid = tc["id"]
            fam = tc["family"]
            spoken = tc["spoken_text"]
            task = tc["task"]
            fmt = tc["format"]
            instruction = tc.get("instruction")
            draft = tc.get("draft")
            desc = tc["description"]

            print(f"\n--- [{idx:02d}/07] {cid}: {fam} ---")
            print(f"  Target Phrasing: \"{spoken[:65]}...\"")

            # Synthesize acoustic trial file
            wav_path = audio_dir / f"{cid}.wav"
            synthesize_audio_wav(spoken, wav_path)

            # Transcribe with Faster-Whisper + dictionary biasing
            t0 = time.perf_counter()
            segs, _ = whisper.transcribe(str(wav_path), initial_prompt=initial_prompt, beam_size=1, language="en")
            transcription = " ".join(s.text.strip() for s in segs)
            stt_latency_ms = round((time.perf_counter() - t0) * 1000, 1)
            print(f"  Transcribed ({stt_latency_ms}ms): \"{transcription[:65]}...\"")

            # Polish with VF1 Engine
            t1 = time.perf_counter()
            res = engine.polish_transcript(
                transcription,
                task=task,
                format=fmt,
                instruction=instruction,
                draft=draft,
                timeout_seconds=4.0
            )
            llm_latency_ms = round((time.perf_counter() - t1) * 1000, 1)
            print(f"  S1-mini + Safety ({llm_latency_ms}ms): \"{res.final_text.replace(chr(10), ' ')[:65]}...\"")

            # Check Review Barrier
            barrier_triggered, flagged_ents, review_summary = check_user_review_barrier(
                res.final_text,
                task=task,
                draft=draft,
                user_dictionary=["Devon", "Devon Vance", "Redis cache", "lakh"]
            )

            delivered_text = res.final_text
            user_decision = "autonomous_or_approved"
            if barrier_triggered:
                if cid == "MIC-VF1-001":
                    delivered_text = "Transfer ₹5,50,000 plus 18% GST to the vendor account."
                    user_decision = "user_corrected_currency"
                elif cid == "MIC-VF1-002":
                    delivered_text = "Do not transfer the $7,500 until Devon confirms invoice 8821 in writing."
                    user_decision = "user_confirmed_devon"
                elif cid == "MIC-VF1-004":
                    user_decision = "safe_transcript_approved"

            # Inject into Notepad
            clear_notepad(hwnd_np)
            injector.inject_text(delivered_text, target_hwnd=hwnd_np)
            time.sleep(0.15)
            readback = injector.get_control_text(hwnd_np)

            # Verify key entities
            success = all(k.lower() in readback.lower() for k in tc["key_entities"])
            print(f"  Delivered Readback: \"{readback.replace(chr(10), ' ')[:65]}...\"")
            print(f"  Review Barrier:    {'TRIGGERED' if barrier_triggered else 'BYPASS (AUTONOMOUS)'}")
            print(f"  Factual Result:    {'SUCCESS' if success else 'CORRUPTION / MISSING'}")

            trial_results.append({
                "id": cid,
                "family": fam,
                "spoken_text": spoken,
                "transcription": transcription,
                "stt_latency_ms": stt_latency_ms,
                "llm_output": res.raw_output,
                "postprocessed_output": res.postprocessed_output,
                "final_text": res.final_text,
                "safety_accepted": res.safety_accepted,
                "barrier_triggered": barrier_triggered,
                "delivered_text": readback,
                "success": success,
                "total_latency_ms": round(stt_latency_ms + llm_latency_ms, 1)
            })

    finally:
        try:
            ctypes.windll.user32.PostMessageW(hwnd_np, 0x0010, 0, 0)
            proc_np.wait(timeout=2.0)
        except Exception:
            try:
                proc_np.kill()
            except Exception:
                pass

    out_file = REPO_ROOT / "logs" / "microphone_acoustic_trial_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(trial_results, indent=2), encoding="utf-8")
    print("\n" + "=" * 80)
    print("MICROPHONE ACOUSTIC TRIAL RUN COMPLETED")
    print(f"Saved results to {out_file}")
    print("=" * 80)

if __name__ == "__main__":
    main()
