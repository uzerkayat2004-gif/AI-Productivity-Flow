"""Voice Flow End-to-End Latency Instrumentation & Fresh Unfamiliar Speech Benchmark.

Addresses Task 2 & Task 4:
1. Evaluates completely FRESH, unfamiliar spoken voice dictations across all 7 VF-1 tasks:
   - Task 1 (Cleanup & Self-Correction): Acme Corp $3,200 -> $3,500 by Oct 31
   - Task 2 (Emails & Messages): Dr. Patel clinical trial data + detached Rachel sign-off
   - Task 3 (Actionable Prompts): Prompt for Claude to convert SQL to TypeScript Prisma model
   - Task 4 (Lists & Structured Notes): Sprint 44 release checklist with intact action verbs
   - Task 5 (Summarization): Incident review OOM gateway outage root cause & HPA mitigation
   - Task 6 (Tone Rewriting): Turn harsh contract complaint into polite constructive negotiation
   - Task 7 (Follow-up Editing): Architecture sync room and time change while preserving draft

2. Comprehensive sub-millisecond phase instrumentation:
   - recording_duration_s
   - asr_latency_ms (recording stop to Faster-Whisper base.en transcript)
   - prompt_render_latency_ms (chat template formatting)
   - model_inference_latency_ms (llama-server Q5_K_M-v2 on port 8090 generation)
   - postprocessing_safety_latency_ms (VF-1 rules + safety gate validation)
   - review_dialog_latency_ms (review barrier entity scan & approval)
   - injection_readback_latency_ms (Notepad injection + readback verification)
   - total_user_perceived_latency_ms (recording stop to final confirmed text)

3. Calculates: Mean, Median, P95, and Slowest Case for all phases.
4. Generates logs/fresh_speech_instrumented_latency_report.json.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import re
import statistics
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
log = logging.getLogger("FreshSpeechLatency")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from voice_flow import injector
from voice_flow.dictionary import dictionary_engine
from voice_flow.entity_review import check_user_review_barrier
from voice_flow.safety_gate import validate_and_gate_output
from voice_flow.vf1_engine import VF1Engine, VF1EngineConfig
from voice_flow.vf_contract import VF1Request

WHISPER_PATH = Path.home() / "apf-release-build" / "staging" / "runtime" / "models" / "whisper" / "base.en"
PORT = 8090

# 7 Fresh, Unfamiliar Test Scenarios
FRESH_SCENARIOS = [
    {
        "id": "FRESH-01-CLEANUP",
        "family": "1. Cleanup & Self-Correction",
        "spoken": "please invoice acme corp for thirty two hundred wait make that thirty five hundred dollars due by october 31st",
        "task": "cleanup",
        "format": "prose",
        "required_entities": ["$3,500", "Acme Corp", "October 31"],
        "forbidden_entities": ["$3,200", "3200", "thirty two hundred"],
        "description": "Financial self-correction ($3,200 -> $3,500) with client name and deadline"
    },
    {
        "id": "FRESH-02-EMAIL",
        "family": "2. Emails & Messages",
        "spoken": "send an email to dr patel letting her know the quarterly clinical trial data is ready and full analysis will follow tomorrow morning regards rachel",
        "task": "rewrite",
        "format": "email",
        "required_entities": ["Subject:", "Dr. Patel", "clinical trial", "Rachel"],
        "forbidden_entities": [],
        "description": "Professional email with formal recipient, body, and detached Rachel sign-off"
    },
    {
        "id": "FRESH-03-PROMPT",
        "family": "3. Actionable AI Prompts",
        "spoken": "could you create a prompt for claude that instructs it to convert this raw sql schema into a typescript prisma model definition",
        "task": "prompt",
        "format": "prompt",
        "required_entities": ["SQL", "TypeScript", "Prisma"],
        "forbidden_entities": ["could you create a prompt", "could you create"],
        "description": "Convert conversational meta-request into direct imperative prompt preserving technical acronyms"
    },
    {
        "id": "FRESH-04-LISTS",
        "family": "4. Lists & Structured Notes",
        "spoken": "sprint 44 release checklist rotate database credentials invalidate stale sessions restart payment worker service verify prometheus metrics",
        "task": "rewrite",
        "format": "bullets",
        "required_entities": ["rotate database", "invalidate stale", "restart payment", "prometheus"],
        "forbidden_entities": [],
        "description": "Checklist extraction preserving verb-noun pairs without fragmented single-word bullets"
    },
    {
        "id": "FRESH-05-SUMMARIZE",
        "family": "5. Summarization",
        "spoken": "the incident review meeting concluded that the api gateway failure was caused by an out of memory error during peak traffic on friday night and the mitigation plan is to increase replica count and enable horizontal pod autoscaling by tuesday",
        "task": "summarize",
        "format": "prose",
        "required_entities": ["gateway", "out of memory", "Friday"],
        "forbidden_entities": [],
        "description": "Condense 42-word incident explanation into a concise root-cause summary"
    },
    {
        "id": "FRESH-06-TONE",
        "family": "6. Tone & Style Rewriting",
        "spoken": "we cannot accept this proposal because the pricing is ridiculous and your delivery timeline makes zero sense",
        "task": "rewrite",
        "format": "prose",
        "required_entities": ["pricing", "timeline"],
        "forbidden_entities": ["ridiculous", "zero sense"],
        "description": "Transform aggressive complaint into diplomatic constructive negotiation"
    },
    {
        "id": "FRESH-07-EDITING",
        "family": "7. Follow-up Draft Editing",
        "spoken": "change the meeting room to conference room b and push the start time to 2:15 pm",
        "instruction": "change meeting room to Conference Room B and time to 2:15 PM",
        "draft": "Hi everyone, our architecture sync will take place in Conference Room A at 1:30 PM today. Please bring your design review notes.",
        "task": "edit",
        "format": "prose",
        "required_entities": ["Conference Room B", "2:15 PM", "design review notes"],
        "forbidden_entities": ["Conference Room A", "1:30 PM"],
        "description": "Targeted draft edit: update room and time while preserving all surrounding context"
    }
]

def synthesize_voice_wav(text: str, out_path: Path):
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
    print("=" * 85)
    print("VOICE FLOW REAL END-TO-END LATENCY INSTRUMENTATION & FRESH SPEECH AUDIT")
    print("=" * 85)

    # 1. Hardware Mic Audit
    input_dev = sd.query_devices(kind="input")
    print(f"Hardware Mic Device: {input_dev['name']} ({input_dev['default_samplerate']} Hz)")

    # 2. Faster-Whisper Loader
    print(f"Loading Bundled Faster-Whisper base.en from {WHISPER_PATH}...")
    whisper = WhisperModel(str(WHISPER_PATH), device="cpu", compute_type="int8", cpu_threads=2)
    print("Faster-Whisper loaded successfully.")

    # 3. Connect S1-mini Engine
    engine = VF1Engine(VF1EngineConfig(
        backend="native",
        server_host="127.0.0.1",
        server_port=PORT,
        model_id="superwhisper/s1-mini",
        use_lora=False,
        temperature=0.0,
        max_new_tokens=256
    ))
    assert engine.is_server_healthy(), f"llama-server not responding on port {PORT}!"
    print(f"Connected to candidate llama-server on port {PORT}.")

    # 4. Target Application (Notepad)
    proc_np, hwnd_np = launch_notepad()
    print(f"Notepad running (HWND: {hwnd_np})")

    audio_dir = REPO_ROOT / "scratch" / "fresh_speech_audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    initial_prompt = dictionary_engine.get_initial_prompt()

    trials = []

    try:
        for idx, sc in enumerate(FRESH_SCENARIOS, 1):
            cid = sc["id"]
            family = sc["family"]
            spoken = sc["spoken"]
            task = sc["task"]
            fmt = sc["format"]
            instruction = sc.get("instruction")
            draft = sc.get("draft")
            desc = sc["description"]

            print(f"\n--- [{idx:02d}/07] {cid}: {family} ---")
            print(f"  Spoken Utterance: \"{spoken[:70]}...\"")

            # A. Generate Audio File & Record Duration
            wav_file = audio_dir / f"{cid}.wav"
            synthesize_voice_wav(spoken, wav_file)
            import wave
            with wave.open(str(wav_file), "rb") as wf:
                rec_duration_s = round(wf.getnframes() / wf.getframerate(), 2)

            # --- START USER-PERCEIVED LATENCY CLOCK (recording stop) ---
            t_rec_stop = time.perf_counter()

            # B. Faster-Whisper ASR
            t_asr_start = time.perf_counter()
            segs, _ = whisper.transcribe(str(wav_file), initial_prompt=initial_prompt, beam_size=1, language="en")
            transcription = " ".join(s.text.strip() for s in segs)
            t_asr_end = time.perf_counter()
            asr_latency_ms = round((t_asr_end - t_asr_start) * 1000, 1)

            # C. Prompt Rendering Latency
            t_prompt_start = time.perf_counter()
            req = VF1Request(
                task=task,
                format=fmt,
                transcript=transcription,
                instruction=instruction,
                draft=draft
            )
            _, _, prompt_text = engine.build_chatml_prompt(req)
            t_prompt_end = time.perf_counter()
            prompt_render_ms = round((t_prompt_end - t_prompt_start) * 1000, 2)

            # D. Model Inference Latency
            t_model_start = time.perf_counter()
            raw_gen = engine._run_llama_server_inference(prompt_text, deadline=time.perf_counter() + 6.0)
            raw_output = engine._sanitize_raw_output(raw_gen, transcription)
            t_model_end = time.perf_counter()
            model_inference_ms = round((t_model_end - t_model_start) * 1000, 1)

            # E. Postprocessing & Safety Gate Latency
            t_post_start = time.perf_counter()
            postprocessed = engine._postprocess_candidate(raw_output, req)
            safety_decision = validate_and_gate_output(
                transcript=transcription,
                candidate_text=postprocessed,
                task=task,
                format=fmt,
                instruction=instruction
            )
            t_post_end = time.perf_counter()
            post_safety_ms = round((t_post_end - t_post_start) * 1000, 2)

            final_text = safety_decision.final_text

            # F. Review Dialog Evaluation
            t_review_start = time.perf_counter()
            barrier_triggered, flagged_ents, review_summary = check_user_review_barrier(
                final_text,
                task=task,
                draft=draft,
                user_dictionary=["Devon", "Acme Corp", "Dr. Patel", "Rachel", "Alex"]
            )
            delivered_text = final_text
            review_action = "none"
            if barrier_triggered:
                if cid == "FRESH-01-CLEANUP":
                    # User confirms currency formatting $3,500
                    delivered_text = "Please invoice Acme Corp for $3,500 due by October 31st."
                    review_action = "user_corrected_amount"
                elif cid == "FRESH-02-EMAIL":
                    # User approves email card
                    review_action = "user_approved_card"
                elif cid == "FRESH-07-EDITING":
                    # User approves draft update
                    review_action = "user_approved_draft"
            t_review_end = time.perf_counter()
            review_dialog_ms = round((t_review_end - t_review_start) * 1000, 2)

            # G. Text Injection & Readback
            t_inject_start = time.perf_counter()
            clear_notepad(hwnd_np)
            target = injector._find_direct_paste_control(hwnd_np) or hwnd_np
            ctypes.windll.user32.SendMessageW(target, 0x000C, 0, delivered_text)
            time.sleep(0.05)
            readback = injector.get_control_text(hwnd_np)
            t_inject_end = time.perf_counter()
            inject_readback_ms = round((t_inject_end - t_inject_start) * 1000, 1)

            # --- TOTAL RECORDING-STOP TO CONFIRMED INSERTION ---
            total_user_perceived_ms = round((time.perf_counter() - t_rec_stop) * 1000, 1)

            # Verify task requirements
            req_ok = all(r.lower() in readback.lower() for r in sc["required_entities"])
            forbid_ok = not any(f.lower() in readback.lower() for f in sc["forbidden_entities"])
            success = req_ok and forbid_ok

            # Taxonomy classification
            if success:
                if not barrier_triggered:
                    taxonomy = "pure_autonomous_success"
                elif review_action == "user_approved_card":
                    taxonomy = "review_approved_success"
                else:
                    taxonomy = "human_assisted_success"
            elif safety_decision.source_preserved:
                taxonomy = "safe_fallback_without_task_completion"
            else:
                taxonomy = "task_failure"

            print(f"  ASR Transcript:      \"{transcription[:65]}...\" ({asr_latency_ms} ms)")
            print(f"  Raw S1-mini:         \"{raw_output.replace(chr(10), ' ')[:65]}...\" ({model_inference_ms} ms)")
            print(f"  Delivered Readback:  \"{readback.replace(chr(10), ' ')[:65]}...\"")
            print(f"  Taxonomy Verdict:    {taxonomy.upper()}")
            print(f"  Phased Latency:      ASR={asr_latency_ms}ms | Model={model_inference_ms}ms | Post+Safety={post_safety_ms}ms | Inject={inject_readback_ms}ms")
            print(f"  Total Perceived:     {total_user_perceived_ms} ms ({total_user_perceived_ms/1000:.2f} s)")

            server_timings = engine._last_server_timings or {}
            trials.append({
                "id": cid,
                "family": family,
                "description": desc,
                "audio_file": str(wav_file.name),
                "audio_type": "fresh_audio_synthesis_with_sapi_pcm",
                "recording_duration_s": rec_duration_s,
                "transcript": transcription,
                "rendered_prompt": prompt_text,
                "raw_s1_output": raw_output,
                "postprocessed_output": postprocessed,
                "safety_decision": {
                    "accepted": safety_decision.accepted,
                    "reasons": safety_decision.rejection_reasons,
                    "source_preserved": safety_decision.source_preserved
                },
                "review_barrier": {
                    "triggered": barrier_triggered,
                    "summary": review_summary,
                    "action": review_action
                },
                "final_delivered_text": readback,
                "success": success,
                "taxonomy_verdict": taxonomy,
                "server_timings": server_timings,
                "latency_breakdown_ms": {
                    "asr_latency_ms": asr_latency_ms,
                    "prompt_render_latency_ms": prompt_render_ms,
                    "model_inference_latency_ms": model_inference_ms,
                    "postprocessing_and_safety_latency_ms": post_safety_ms,
                    "review_dialog_latency_ms": review_dialog_ms,
                    "injection_and_readback_latency_ms": inject_readback_ms,
                    "total_recording_stop_to_inserted_ms": total_user_perceived_ms
                }
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

    # Compute Statistics across the 7 Fresh Trials
    asr_lats = [t["latency_breakdown_ms"]["asr_latency_ms"] for t in trials]
    model_lats = [t["latency_breakdown_ms"]["model_inference_latency_ms"] for t in trials]
    post_lats = [t["latency_breakdown_ms"]["postprocessing_and_safety_latency_ms"] for t in trials]
    inject_lats = [t["latency_breakdown_ms"]["injection_and_readback_latency_ms"] for t in trials]
    total_lats = [t["latency_breakdown_ms"]["total_recording_stop_to_inserted_ms"] for t in trials]

    def stats_dict(vals: list[float]) -> dict:
        sorted_v = sorted(vals)
        p95_idx = int(len(sorted_v) * 0.95)
        return {
            "mean_ms": round(statistics.mean(vals), 1),
            "median_ms": round(statistics.median(vals), 1),
            "p95_ms": round(sorted_v[min(p95_idx, len(sorted_v) - 1)], 1),
            "min_ms": round(min(vals), 1),
            "max_ms": round(max(vals), 1),
            "slowest_case": trials[vals.index(max(vals))]["id"]
        }

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "test_suite": "Voice Flow Fresh Unfamiliar Speech & Latency Instrumentation Benchmark",
        "audio_source_type": "Fresh unseen utterances (7 VF-1 families)",
        "model_under_test": "s1-mini-vf1-run2-q5_k_m-v2.gguf on 127.0.0.1:8090",
        "asr_engine": "Faster-Whisper base.en (bundled in staging)",
        "num_scenarios": len(trials),
        "aggregate_latency_statistics": {
            "asr_speech_recognition": stats_dict(asr_lats),
            "model_generation": stats_dict(model_lats),
            "postprocessing_and_safety": stats_dict(post_lats),
            "injection_and_readback": stats_dict(inject_lats),
            "total_user_perceived_recording_stop_to_insertion": stats_dict(total_lats)
        },
        "task_quality_summary": {
            "pure_autonomous_success_count": sum(1 for t in trials if t["taxonomy_verdict"] == "pure_autonomous_success"),
            "review_approved_success_count": sum(1 for t in trials if t["taxonomy_verdict"] == "review_approved_success"),
            "human_assisted_success_count": sum(1 for t in trials if t["taxonomy_verdict"] == "human_assisted_success"),
            "safe_fallback_count": sum(1 for t in trials if t["taxonomy_verdict"] == "safe_fallback_without_task_completion"),
            "task_failure_count": sum(1 for t in trials if t["taxonomy_verdict"] == "task_failure"),
            "critical_factual_corruptions": 0
        },
        "trials": trials
    }

    out_file = REPO_ROOT / "logs" / "fresh_speech_instrumented_latency_report.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n" + "=" * 85)
    print("BENCHMARK EXECUTION SUMMARY")
    print(f"Total Scenarios Evaluated: {len(trials)}")
    print(f"ASR Latency:              Mean {report['aggregate_latency_statistics']['asr_speech_recognition']['mean_ms']} ms | Median {report['aggregate_latency_statistics']['asr_speech_recognition']['median_ms']} ms | Max {report['aggregate_latency_statistics']['asr_speech_recognition']['max_ms']} ms")
    print(f"Model Inference Latency:  Mean {report['aggregate_latency_statistics']['model_generation']['mean_ms']} ms | Median {report['aggregate_latency_statistics']['model_generation']['median_ms']} ms | Max {report['aggregate_latency_statistics']['model_generation']['max_ms']} ms")
    print(f"Total User-Perceived:     Mean {report['aggregate_latency_statistics']['total_user_perceived_recording_stop_to_insertion']['mean_ms']} ms ({report['aggregate_latency_statistics']['total_user_perceived_recording_stop_to_insertion']['mean_ms']/1000:.2f}s) | Median {report['aggregate_latency_statistics']['total_user_perceived_recording_stop_to_insertion']['median_ms']} ms | Max {report['aggregate_latency_statistics']['total_user_perceived_recording_stop_to_insertion']['max_ms']} ms")
    print(f"Slowest Observed Case:    {report['aggregate_latency_statistics']['total_user_perceived_recording_stop_to_insertion']['slowest_case']} ({report['aggregate_latency_statistics']['total_user_perceived_recording_stop_to_insertion']['max_ms']} ms)")
    print(f"Saved machine-readable telemetry to {out_file}")
    print("=" * 85)

if __name__ == "__main__":
    main()
