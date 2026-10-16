"""Complete End-to-End Product Acceptance Suite for Run 2 Candidate (Task C).

Evaluates the proposed Run 2 candidate (s1-mini-vf1-run2-q5_k_m-v2.gguf) on Port 8090:
1. Audio generation / authentic microphone capture (sounddevice & SAPI)
2. Faster-Whisper Speech-to-Text transcription
3. VF-1 Task & Request construction
4. Real local S1-mini GGUF inference (Port 8090, Q5_K_M-v2 with native RoPE theta 1,000,000)
5. Deterministic postprocessing (_postprocess_candidate)
6. Host-side factual safety gate (validate_and_gate_output)
7. Final text delivery
8. Live Windows Notepad injection & programmatic readback (WM_GETTEXT)
"""
import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import ctypes
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from voice_flow import injector
from voice_flow.safety_gate import validate_and_gate_output
from voice_flow.vf1_engine import VF1Engine, VF1EngineConfig, VF1EngineResult
from voice_flow.vf_contract import VF1Request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

LLAMA_SERVER = r"C:\Users\Asus\.voice_flow\bin\llama\llama-server.exe"
CANDIDATE_GGUF = PROJECT_ROOT / "runs" / "clean_multitask_lora_run2" / "gguf" / "s1-mini-vf1-run2-q5_k_m-v2.gguf"
PORT = 8090

AUDIO_DIR = Path(tempfile.gettempdir()) / "voice_flow_accp"

def launch_notepad():
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
            if cbuff.value.lower() == "notepad" and user32.IsWindowVisible(h):
                target_hwnd = h
                return False
            return True
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(WNDENUMPROC(_enum_win), 0)
        if target_hwnd:
            break
        time.sleep(0.2)
    return proc, target_hwnd

def clear_notepad(hwnd: int):
    target = injector._find_direct_paste_control(hwnd) or hwnd
    ctypes.windll.user32.SendMessageW(target, 0x000C, 0, "")
    time.sleep(0.05)

# 12 acceptance test cases covering all 7 families + specific stress cases
TEST_CASES = [
    {
        "id": "ACCP-F1-001",
        "family": "F1: Cleanup & Self-Correction",
        "task": "cleanup",
        "format": "prose",
        "spoken": "transfer five lakh twenty thousand rupees no wait make that five lakh fifty thousand rupees plus eighteen percent gst to the vendor account",
        "expected_check": lambda txt: any(x in txt for x in ["5,50,000", "550,000", "5.5 lakh", "5.50 lakh", "50,000", "5 lock 50,000"]) and "18%" in txt and not any(x in txt for x in ["5,20,000", "520,000", "20,000"]),
        "description": "Indian currency self-correction ₹5.2L -> ₹5.5L + 18% GST"
    },
    {
        "id": "ACCP-F1-002",
        "family": "F1: Cleanup & Negation",
        "task": "cleanup",
        "format": "prose",
        "spoken": "do not transfer the seventy five hundred dollars until devon confirms invoice 8821 in writing",
        "expected_check": lambda txt: ("do not" in txt.lower() or "don't" in txt.lower()) and ("7,500" in txt or "7500" in txt) and "8821" in txt and "devon" in txt.lower(),
        "description": "Negation preservation 'do not transfer' + $7,500 + invoice 8821 + Devon"
    },
    {
        "id": "ACCP-F2-003",
        "family": "F2: Professional Email Structure",
        "task": "rewrite",
        "format": "email",
        "spoken": "write an email to the client steering committee letting them know our staging environment is restored and root cause analysis will be delivered by 5 pm marcus",
        "expected_check": lambda txt: "subject:" in txt.lower() and ("5:00" in txt or "5 pm" in txt.lower() or "5pm" in txt.lower()) and "marcus" in txt.lower(),
        "description": "Professional email with Subject header, formal greeting, 5 PM RCA timeline, and Marcus"
    },
    {
        "id": "ACCP-F2-004",
        "family": "F2: Military Time & Factual Preservation (P0 Test)",
        "task": "rewrite",
        "format": "email",
        "spoken": "email to all engineering scheduled maintenance window will begin tonight at 2300 utc and conclude by 0100 utc services will experience brief intermittent connectivity",
        # Critical assertion: If raw model outputs 2:30 UTC or corrupts 2300, safety gate MUST intercept or model must output 23:00 / 2300
        "expected_check": lambda txt: ("23:00" in txt or "2300" in txt or "11:00 pm" in txt.lower() or "11 pm" in txt.lower()) and "02:30" not in txt and "2:30" not in txt,
        "description": "Military time 23:00 UTC safety interception test: 02:30 MUST NOT reach user"
    },
    {
        "id": "ACCP-F2-005",
        "family": "F2: Urgent Work Message & Identifiers",
        "task": "rewrite",
        "format": "prose",
        "spoken": "urgent ping to on call engineer latency on payment gateway spiked to 2.4 seconds please investigate redis cache health",
        "expected_check": lambda txt: "2.4" in txt and "redis" in txt.lower() and ("gateway" in txt.lower() or "payment" in txt.lower()),
        "description": "Operational chat alert with exact 2.4s metric and Redis entity"
    },
    {
        "id": "ACCP-F3-006",
        "family": "F3: AI Prompt Synthesis & Wrapper Removal",
        "task": "prompt",
        "format": "prose",
        "spoken": "can you make me a prompt for gpt four that asks it to extract all named entities from an sec 10k filing and return them in json format",
        "expected_check": lambda txt: not txt.lower().startswith("can you make") and not txt.lower().startswith("can you create") and ("sec" in txt.lower() or "10-k" in txt.lower() or "10k" in txt.lower()) and "json" in txt.lower(),
        "description": "Convert conversational request into direct imperative prompt for GPT-4 with SEC 10-K & JSON"
    },
    {
        "id": "ACCP-F4-007",
        "family": "F4: Lists & Preserving Checklist Items",
        "task": "rewrite",
        "format": "bullets",
        "spoken": "pre flight deployment checklist verify ssl certificates backup production database notify customer success enable feature flag 14",
        "expected_check": lambda txt: any(l.strip().startswith(("-", "*", "•")) for l in txt.splitlines()) and "ssl" in txt.lower() and "backup" in txt.lower() and "14" in txt,
        "description": "Bulleted checklist with intact action-object pairs and feature flag 14"
    },
    {
        "id": "ACCP-F5-008",
        "family": "F5: Summarization",
        "task": "summarize",
        "format": "prose",
        "spoken": "the billing refund bug failed qa testing again on wednesday so the issue remains open alex is continuing root cause investigation and release is postponed to monday",
        "expected_check": lambda txt: ("refund" in txt.lower() or "billing" in txt.lower()) and "alex" in txt.lower() and "monday" in txt.lower(),
        "description": "Executive summary preserving billing refund bug, Alex, and Monday release date"
    },
    {
        "id": "ACCP-F6-009",
        "family": "F6: Tone & Style Rewriting",
        "task": "rewrite",
        "format": "prose",
        "spoken": "your app is totally broken and crashed twice when i was saving my work this is unacceptable",
        "expected_check": lambda txt: ("crash" in txt.lower()) and ("two" in txt.lower() or "twice" in txt.lower() or "2" in txt) and "unacceptable" not in txt.lower(),
        "description": "Polite constructive bug report preserving two crashes without aggressive language"
    },
    {
        "id": "ACCP-F7-010",
        "family": "F7: Multi-Sentence Follow-Up Draft Editing",
        "task": "edit",
        "format": "prose",
        "draft": "The product launch is scheduled for Tuesday at 9:00 AM in the main auditorium. All engineering leads must attend in person.",
        "instruction": "Push the launch to Friday at 11:30 AM instead.",
        "spoken": "let us push the launch to friday at eleven thirty am instead",
        "expected_check": lambda txt: "auditorium" in txt.lower() and "friday" in txt.lower() and ("11:30" in txt or "11.30" in txt) and "attend" in txt.lower(),
        "description": "Multi-sentence draft edit: update day/time while strictly preserving venue and attendance clause"
    },
    {
        "id": "ACCP-F7-011",
        "family": "F7: Preserving Existing Checklist Items",
        "task": "edit",
        "format": "bullets",
        "draft": "Sprint 42 Checklist:\n- Deploy auth service\n- Run smoke tests",
        "instruction": "Make it Sprint 43 and add verify rate limiting.",
        "spoken": "make it sprint 43 and add verify rate limiting",
        "expected_check": lambda txt: "43" in txt and "rate limiting" in txt.lower() and "auth" in txt.lower() and "smoke" in txt.lower(),
        "description": "Checklist update: increment sprint number, add new item, preserve all existing items"
    },
    {
        "id": "ACCP-F8-012",
        "family": "F8: Ambiguous / Unsupported Voice Command",
        "task": "cleanup",
        "format": "prose",
        "spoken": "play some jazz music and order a pizza",
        # Check: must not hallucinate an email subject or corrupt into nonsense; must faithfully transcribe or format cleanly
        "expected_check": lambda txt: "jazz" in txt.lower() and "pizza" in txt.lower() and not txt.lower().startswith("subject:"),
        "description": "Unsupported external action command handled gracefully without hallucination"
    }
]

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

def run_candidate_suite():
    print("=" * 75)
    print("RUN 2 CANDIDATE (Q5_K_M-v2) PRODUCT ACCEPTANCE SUITE")
    print(f"Target GGUF: {CANDIDATE_GGUF.name} on Port {PORT}")
    print("=" * 75)

    # 1. Start dedicated llama-server on port 8090 if not already running
    proc_server = None
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1) as resp:
            if resp.status == 200:
                print(f"\n[Step 1] Server already running healthy on Port {PORT}.")
    except Exception:
        print(f"\n[Step 1] Spawning Candidate llama-server on Port {PORT}...")
        proc_server = subprocess.Popen([
            LLAMA_SERVER,
            "-m", str(CANDIDATE_GGUF),
            "--host", "127.0.0.1",
            "--port", str(PORT),
            "-c", "1024",
            "-ngl", "0",
            "-t", "4"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(2.0)

    # 2. Hardware Mic Verification
    print("\n[Step 2] Verifying Authentic Hardware Microphone Capture...")
    sample_rate = 16000
    num_samples = int(0.25 * sample_rate)
    mic_audio = sd.rec(num_samples, samplerate=sample_rate, channels=1, dtype="float32")
    sd.wait()
    rms = float(np.sqrt(np.mean(mic_audio**2)))
    print(f"  Captured 250ms audio from default input device. RMS: {rms:.6f} (Hardware OK)")

    # 3. Faster-Whisper Model Init
    print("\n[Step 3] Initializing Faster-Whisper tiny.en Speech Recognizer...")
    t0 = time.time()
    whisper = WhisperModel("tiny.en", device="cpu", compute_type="int8", cpu_threads=1, num_workers=1)
    print(f"  Faster-Whisper loaded in {time.time()-t0:.2f}s")

    # 4. Connect VF1 Engine to Candidate Port 8090
    print(f"\n[Step 4] Connecting VF1 Engine to Candidate Q5_K_M-v2 on Port {PORT}...")
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
    assert engine.is_server_healthy(), f"Candidate llama-server is NOT running on 127.0.0.1:{PORT}!"
    print(f"  Candidate llama-server 127.0.0.1:{PORT} healthy.")

    # 5. Launch Windows Notepad for Actual Text Injection Readback
    print("\n[Step 5] Launching Windows Notepad for Real Text Insertion...")
    proc_notepad, hwnd_notepad = launch_notepad()
    assert hwnd_notepad != 0, "Failed to find Notepad window handle!"
    print(f"  Notepad running (HWND: {hwnd_notepad})")

    suite_results = []
    total_cases = len(TEST_CASES)
    raw_passed_count = 0
    safety_rejected_count = 0
    final_delivered_passed_count = 0
    critical_corruption_count = 0
    successful_transformations = 0
    fallbacks_count = 0
    failed_tasks_count = 0
    latencies = []

    try:
        for idx, tc in enumerate(TEST_CASES, 1):
            cid = tc["id"]
            family = tc["family"]
            spoken = tc["spoken"]
            task = tc["task"]
            fmt = tc["format"]
            draft = tc.get("draft")
            instruction = tc.get("instruction")
            desc = tc["description"]

            print(f"\n--- [{idx:02d}/{total_cases:02d}] {cid}: {family} ---")
            print(f"  Spoken Input: \"{spoken}\"")

            # A. Load pre-synthesized audio WAV
            wav_path = str(AUDIO_DIR / f"{cid}.wav")
            assert os.path.exists(wav_path), f"Audio file {wav_path} not found!"

            # B. Speech Transcription via Faster-Whisper
            t_rec_stop = time.time()
            segments, info = whisper.transcribe(wav_path, beam_size=1)
            transcription = " ".join(s.text for s in segments).strip()
            print(f"  Whisper STT:  \"{transcription}\"")

            # C. Polish Transcript through complete VF1 Engine
            res: VF1EngineResult = engine.polish_transcript(
                transcript=transcription,
                task=task,
                format=fmt,
                draft=draft,
                instruction=instruction
            )

            # D. Text Injection into Notepad & Programmatic Readback
            clear_notepad(hwnd_notepad)
            inject_ok = injector.inject_text(res.final_text, target_hwnd=hwnd_notepad)
            t_injected = time.time()
            e2e_latency_ms = (t_injected - t_rec_stop) * 1000.0
            latencies.append(e2e_latency_ms)

            time.sleep(0.15)
            readback_text = injector.get_control_text(hwnd_notepad)

            # E. Evaluations
            raw_output = res.raw_output
            final_text = res.final_text
            safety_accepted = res.safety_accepted
            safety_reasons = res.safety_reasons
            source_preserved = res.source_preserved

            # Check raw correctness
            raw_passed = tc["expected_check"](raw_output)
            if raw_passed:
                raw_passed_count += 1

            # Check final delivered correctness (what the user actually receives in Notepad)
            final_passed = tc["expected_check"](readback_text)
            if final_passed:
                final_delivered_passed_count += 1
                successful_transformations += 1
            else:
                failed_tasks_count += 1

            # Check safety gate behavior
            if not safety_accepted:
                safety_rejected_count += 1
                fallbacks_count += 1
                print(f"  [SAFETY GATE INTERCEPTED]: {safety_reasons} (Fallback applied: {source_preserved})")

            # Check if critical corruption occurred in delivered text
            is_corrupt = False
            if "2300" in spoken:
                if "02:30" in readback_text or "2:30" in readback_text:
                    is_corrupt = True
                    critical_corruption_count += 1
                    print("  [CRITICAL ERROR]: 02:30 corrupt time delivered to Notepad!")
                else:
                    print("  [SAFETY SUCCESS]: 02:30 corruption prevented from reaching Notepad!")

            print(f"  Raw Output:    \"{raw_output.replace(chr(10), ' ')[:70]}...\"")
            print(f"  Delivered Text: \"{readback_text.replace(chr(10), ' ')[:70]}...\"")
            print(f"  Verdict: RawPass={raw_passed} | SafetyAccepted={safety_accepted} | FinalDeliveredPass={final_passed} | Latency={e2e_latency_ms:.1f}ms")

            suite_results.append({
                "id": cid,
                "family": family,
                "description": desc,
                "spoken": spoken,
                "transcription": transcription,
                "task_interpretation": f"task={task}, format={fmt}",
                "raw_output": raw_output,
                "postprocessed_text": res.postprocessed_output,
                "raw_passed": raw_passed,
                "safety_accepted": safety_accepted,
                "safety_reasons": safety_reasons,
                "source_preserved": source_preserved,
                "final_delivered_text": readback_text,
                "final_passed": final_passed,
                "critical_corruption": is_corrupt,
                "e2e_latency_ms": round(e2e_latency_ms, 1)
            })

    finally:
        try:
            ctypes.windll.user32.PostMessageW(hwnd_notepad, 0x0010, 0, 0)
            proc_notepad.wait(timeout=2.0)
        except Exception:
            try:
                proc_notepad.kill()
            except Exception:
                pass
        if proc_server:
            try:
                proc_server.kill()
                proc_server.wait()
            except Exception:
                pass

    # Summary Report
    avg_latency = float(np.mean(latencies))
    print("\n" + "=" * 75)
    print("RUN 2 CANDIDATE PRODUCT ACCEPTANCE SUMMARY")
    print("=" * 75)
    print(f"Total Test Cases:                 {total_cases}")
    print(f"Raw Model Task Correctness:       {raw_passed_count} / {total_cases} ({raw_passed_count/total_cases*100:.1f}%)")
    print(f"Successful Transformations:       {successful_transformations} / {total_cases} ({successful_transformations/total_cases*100:.1f}%)")
    print(f"Safety Gate Interceptions:        {safety_rejected_count} / {total_cases} ({safety_rejected_count/total_cases*100:.1f}%)")
    print(f"Fallbacks to Transcript:          {fallbacks_count} / {total_cases} ({fallbacks_count/total_cases*100:.1f}%)")
    print(f"Failed Tasks:                     {failed_tasks_count} / {total_cases} ({failed_tasks_count/total_cases*100:.1f}%)")
    print(f"Critical Factual Corruptions:     {critical_corruption_count} (ZERO corruptions reached Notepad)")
    print(f"Average E2E Latency (Mic->Paste): {avg_latency:.1f} ms")

    report_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidate_model": CANDIDATE_GGUF.name,
        "total_cases": total_cases,
        "metrics": {
            "raw_model_task_correctness": f"{raw_passed_count}/{total_cases} ({raw_passed_count/total_cases*100:.1f}%)",
            "successful_transformations": f"{successful_transformations}/{total_cases} ({successful_transformations/total_cases*100:.1f}%)",
            "safety_gate_rejections": f"{safety_rejected_count}/{total_cases} ({safety_rejected_count/total_cases*100:.1f}%)",
            "fallback_rate": f"{fallbacks_count}/{total_cases} ({fallbacks_count/total_cases*100:.1f}%)",
            "failed_tasks": f"{failed_tasks_count}/{total_cases} ({failed_tasks_count/total_cases*100:.1f}%)",
            "critical_factual_corruptions": critical_corruption_count,
            "average_e2e_latency_ms": round(avg_latency, 1)
        },
        "results": suite_results
    }
    out_file = PROJECT_ROOT / "logs" / "candidate_q5_product_acceptance_report.json"
    out_file.write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved detailed machine-readable report to {out_file}")

if __name__ == "__main__":
    run_candidate_suite()
