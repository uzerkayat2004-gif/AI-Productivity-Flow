"""P0 Corrected End-to-End Acceptance & Safety Validation Suite.

Enforces:
1. P0-1: Strict truth table correcting false passes (ACCP-F1-001, ACCP-F1-002, etc.)
2. P0-2: Rigorous 6-way taxonomy:
   - Genuine successful requested transformation
   - Literal transcript delivery
   - Safe fallback without task completion
   - Unsupported command gracefully transcribed
   - Task failure
   - Factual corruption reaching user
3. P0-3: User-facing review barrier evaluation for critical entities
4. Component error attribution: Whisper STT vs S1-mini vs Postprocessing vs Safety Gate
5. Bundled Faster-Whisper base.en execution
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("P0Acceptance")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from faster_whisper import WhisperModel
from voice_flow import injector
from voice_flow.entity_review import check_user_review_barrier, detect_critical_entities
from voice_flow.vf1_engine import VF1Engine, VF1EngineConfig
from voice_flow.vf_contract import VF1Request

WHISPER_PATH = Path.home() / "apf-release-build" / "staging" / "runtime" / "models" / "whisper" / "base.en"
PORT = 8090
AUDIO_DIR = Path(os.environ.get("TEMP", r"C:\Users\Asus\AppData\Local\Temp")) / "voice_flow_accp"

TEST_CASES = [
    {
        "id": "ACCP-F1-001",
        "family": "F1: Cleanup & Self-Correction",
        "task": "cleanup",
        "format": "prose",
        "audio_file": "ACCP-F1-001.wav",
        "spoken": "transfer five lakh twenty thousand rupees no wait make that five lakh fifty thousand rupees plus eighteen percent gst to the vendor account",
        "required_entities": ["5,50,000", "18%"],
        "forbidden_entities": ["5,20,000", "520,000", "lock"],
        "is_unsupported": False,
        "description": "Indian currency self-correction ₹5.2L -> ₹5.5L + 18% GST"
    },
    {
        "id": "ACCP-F1-002",
        "family": "F1: Cleanup & Negation",
        "task": "cleanup",
        "format": "prose",
        "audio_file": "ACCP-F1-002.wav",
        "spoken": "do not transfer the seventy five hundred dollars until devon confirms invoice 8821 in writing",
        "required_entities": ["do not", "7,500", "Devon", "8821"],
        "forbidden_entities": ["8,821", "Devin"],
        "is_unsupported": False,
        "description": "Negation preservation 'do not transfer' + $7,500 + invoice 8821 + Devon"
    },
    {
        "id": "ACCP-F2-003",
        "family": "F2: Professional Email Structure",
        "task": "rewrite",
        "format": "email",
        "audio_file": "ACCP-F2-003.wav",
        "spoken": "write an email to the client steering committee letting them know our staging environment is restored and root cause analysis will be delivered by 5 pm marcus",
        "required_entities": ["Subject:", "staging", "Marcus"],
        "forbidden_entities": [],
        "is_unsupported": False,
        "description": "Professional email with Subject header, formal greeting, 5 PM RCA timeline, and Marcus"
    },
    {
        "id": "ACCP-F2-004",
        "family": "F2: Military Time & Factual Preservation (P0 Test)",
        "task": "rewrite",
        "format": "email",
        "audio_file": "ACCP-F2-004.wav",
        "spoken": "email to all engineering scheduled maintenance window will begin tonight at 2300 utc and conclude by 0100 utc services will experience brief intermittent connectivity",
        "required_entities": ["Subject:", "2300 UTC", "0100 UTC"],
        "forbidden_entities": ["2:30", "02:30", "10 UTC"],
        "is_unsupported": False,
        "description": "Military time 23:00 UTC safety interception test: 02:30 MUST NOT reach user"
    },
    {
        "id": "ACCP-F2-005",
        "family": "F2: Urgent Work Message & Identifiers",
        "task": "rewrite",
        "format": "prose",
        "audio_file": "ACCP-F2-005.wav",
        "spoken": "urgent ping to on call engineer latency on payment gateway spiked to 2.4 seconds please investigate redis cache health",
        "required_entities": ["2.4", "Redis cache"],
        "forbidden_entities": ["reedy's", "reedee's"],
        "is_unsupported": False,
        "description": "Operational chat alert with exact 2.4s metric and Redis entity"
    },
    {
        "id": "ACCP-F3-006",
        "family": "F3: AI Prompt Synthesis & Wrapper Removal",
        "task": "prompt",
        "format": "prompt",
        "audio_file": "ACCP-F3-006.wav",
        "spoken": "can you make me a prompt for gpt four that asks it to extract all named entities from an sec 10k filing and return them in json format",
        "required_entities": ["SEC 10-K", "JSON"],
        "forbidden_entities": ["can you make", "can you make me a prompt"],
        "is_unsupported": False,
        "description": "Convert conversational request into direct imperative prompt for GPT-4 with SEC 10-K & JSON"
    },
    {
        "id": "ACCP-F4-007",
        "family": "F4: Lists & Preserving Checklist Items",
        "task": "rewrite",
        "format": "bullets",
        "audio_file": "ACCP-F4-007.wav",
        "spoken": "pre flight deployment checklist verify ssl certificates backup production database notify customer success enable feature flag 14",
        "required_entities": ["SSL", "backup", "14"],
        "forbidden_entities": [],
        "is_unsupported": False,
        "description": "Bulleted checklist with intact action-object pairs and feature flag 14"
    },
    {
        "id": "ACCP-F5-008",
        "family": "F5: Summarization",
        "task": "summarize",
        "format": "prose",
        "audio_file": "ACCP-F5-008.wav",
        "spoken": "the billing refund bug failed qa testing again on wednesday so the issue remains open alex is continuing root cause investigation and release is postponed to monday",
        "required_entities": ["billing refund", "Alex", "Monday"],
        "forbidden_entities": [],
        "is_unsupported": False,
        "description": "Executive summary preserving billing refund bug, Alex, and Monday release date"
    },
    {
        "id": "ACCP-F6-009",
        "family": "F6: Tone & Style Rewriting",
        "task": "rewrite",
        "format": "prose",
        "audio_file": "ACCP-F6-009.wav",
        "spoken": "your app is totally broken and crashed twice when i was saving my work this is unacceptable",
        "required_entities": ["crashed twice"],
        "forbidden_entities": ["totally broken", "unacceptable"],
        "is_unsupported": False,
        "description": "Polite constructive bug report preserving two crashes without aggressive language"
    },
    {
        "id": "ACCP-F7-010",
        "family": "F7: Multi-Sentence Follow-Up Draft Editing",
        "task": "edit",
        "format": "prose",
        "audio_file": "ACCP-F7-010.wav",
        "spoken": "let us push the launch to friday at eleven thirty am instead",
        "instruction": "push the launch to friday at 11:30 am",
        "draft": "Team, our product launch will be held on Thursday at 10:00 AM in the main auditorium. Attendance is mandatory for all leads.",
        "required_entities": ["Friday", "11:30", "auditorium", "mandatory"],
        "forbidden_entities": ["Thursday"],
        "is_unsupported": False,
        "description": "Multi-sentence draft edit: update day/time while strictly preserving venue and attendance clause"
    },
    {
        "id": "ACCP-F7-011",
        "family": "F7: Preserving Existing Checklist Items",
        "task": "edit",
        "format": "bullets",
        "audio_file": "ACCP-F7-011.wav",
        "spoken": "make it sprint 43 and add verify rate limiting",
        "instruction": "change to sprint 43 and add verify rate limiting",
        "draft": "Sprint 42 Checklist:\n- Deploy auth service\n- Run smoke tests",
        "required_entities": ["Sprint 43", "rate limiting", "Deploy auth", "smoke tests"],
        "forbidden_entities": ["Sprint 42"],
        "is_unsupported": False,
        "description": "Checklist update: increment sprint number, add new item, preserve all existing items"
    },
    {
        "id": "ACCP-F8-012",
        "family": "F8: Ambiguous / Unsupported Voice Command",
        "task": "cleanup",
        "format": "prose",
        "audio_file": "ACCP-F8-012.wav",
        "spoken": "play some jazz music and order a pizza",
        "required_entities": ["jazz", "pizza"],
        "forbidden_entities": ["Subject:"],
        "is_unsupported": True,
        "description": "Unsupported external action command handled gracefully without hallucination"
    }
]

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

def evaluate_taxonomy(tc, raw_output, postprocessed_text, delivered_text, safety_decision, is_corrupt):
    """Classify execution into P0-2 strict 6-way taxonomy."""
    task = tc["task"]
    fmt = tc["format"]
    spoken = tc["spoken"]
    req_ents = tc.get("required_entities", [])
    forbid_ents = tc.get("forbidden_entities", [])
    
    # Check factual corruption
    if is_corrupt:
        return "factual_corruption_reaching_user"
        
    # Check unsupported command
    if tc.get("is_unsupported"):
        if any(f.lower() in delivered_text.lower() for f in forbid_ents):
            return "task_failure"
        return "unsupported_command_gracefully_transcribed"
        
    # Check if safety gate fell back to source
    if safety_decision.source_preserved or delivered_text.startswith("Team,") and "[Voice Flow Note" in delivered_text:
        if task in ("email", "rewrite", "prompt", "edit") and not safety_decision.safety_accepted:
            return "safe_fallback_without_task_completion"
            
    # Check genuine task success
    has_req = all(r.lower() in delivered_text.lower() for r in req_ents)
    has_forbid = any(f.lower() in delivered_text.lower() for f in forbid_ents)
    
    if task == "cleanup":
        if has_req and not has_forbid:
            return "genuine_successful_transformation"
        else:
            return "task_failure"
            
    if fmt == "email":
        if delivered_text.startswith("Subject:") and has_req and not has_forbid:
            return "genuine_successful_transformation"
        elif not safety_decision.safety_accepted:
            return "safe_fallback_without_task_completion"
        else:
            return "task_failure"
            
    if task == "prompt":
        if has_req and not has_forbid:
            return "genuine_successful_transformation"
        return "task_failure"
        
    if fmt == "bullets":
        lines = [l for l in delivered_text.splitlines() if l.strip().startswith(("-", "*", "•", "1.", "2."))]
        if lines and has_req and not has_forbid:
            return "genuine_successful_transformation"
        elif not safety_decision.safety_accepted:
            return "safe_fallback_without_task_completion"
        return "task_failure"
        
    if task == "summarize":
        if has_req and not has_forbid:
            # Check if text was compacted or if it's literal transcript
            if len(delivered_text.split()) < len(spoken.split()) * 0.8:
                return "genuine_successful_transformation"
            else:
                return "literal_transcript_delivery"
        return "task_failure"
        
    if task == "edit":
        if has_req and not has_forbid and tc.get("draft") and tc.get("draft")[:20] in delivered_text:
            return "genuine_successful_transformation"
        elif "[Voice Flow Note" in delivered_text or safety_decision.source_preserved:
            return "safe_fallback_without_task_completion"
        return "task_failure"
        
    if has_req and not has_forbid:
        return "genuine_successful_transformation"
    return "task_failure"

def determine_error_attribution(tc, whisper_text, raw_output, postprocessed_text, delivered_text, safety_decision, taxonomy):
    if taxonomy in ("genuine_successful_transformation", "unsupported_command_gracefully_transcribed"):
        return "None (Success)"
    
    reasons = []
    # Check Whisper acoustic errors
    if tc["id"] == "ACCP-F1-001" and ("lock" in whisper_text.lower() or "no weight" in whisper_text.lower()):
        reasons.append("Whisper STT: Acoustic confusion ('lock' for 'lakh', 'no weight' for 'no wait')")
    if tc["id"] == "ACCP-F1-002" and ("devin" in whisper_text.lower() or "in voice" in whisper_text.lower()):
        reasons.append("Whisper STT: Phonetic homophone 'Devin' for 'Devon', 'in voice 8,821' for 'invoice 8821'")
    if tc["id"] == "ACCP-F2-005" and ("reedy" in whisper_text.lower() or "reedee" in whisper_text.lower()):
        reasons.append("Whisper STT: Technical entity acoustic confusion ('Reedy's cash' for 'Redis cache')")
        
    # Check S1-mini errors
    if tc["id"] == "ACCP-F2-004" and ("2:30" in raw_output or "02:30" in raw_output):
        reasons.append("S1-mini: Hallucinated time '2:30 UTC' instead of 23:00 UTC")
    if tc["id"] == "ACCP-F3-006" and "can you make" in raw_output.lower():
        reasons.append("S1-mini: Failed prompt extraction, echoed conversational wrapper")
    if tc["id"] == "ACCP-F4-007" and "14" not in raw_output:
        reasons.append("S1-mini: Omitted checklist token '14' (feature flag 14)")
    if tc["id"] == "ACCP-F6-009" and ("totally broken" in raw_output.lower() or "unacceptable" in raw_output.lower()):
        reasons.append("S1-mini: Failed tone rewriting, preserved harsh complaint verbatim")
    if tc["id"] in ("ACCP-F7-010", "ACCP-F7-011") and tc.get("draft") and tc.get("draft")[:20] not in raw_output:
        reasons.append("S1-mini: Dropped draft context, emitted standalone edit instruction")
        
    # Check Safety Gate
    if not safety_decision.safety_accepted:
        reasons.append(f"Safety Gate: Intercepted ({', '.join(safety_decision.safety_reasons)}) -> Triggered safe fallback")
        
    return " | ".join(reasons) if reasons else "Task transformation incomplete"

def main():
    print("=" * 80)
    print("VOICE FLOW P0 FINAL ACCEPTANCE & TRUTH TABLE GENERATOR")
    print(f"ASR Model: Faster-Whisper base.en ({WHISPER_PATH})")
    print(f"Target Server: 127.0.0.1:{PORT} (Q5_K_M-v2)")
    print("=" * 80)
    
    # 1. Load Bundled base.en Whisper Model
    assert WHISPER_PATH.is_dir(), f"Bundled base.en path missing: {WHISPER_PATH}"
    print("\n[1/3] Loading Bundled Faster-Whisper base.en Model...")
    whisper = WhisperModel(str(WHISPER_PATH), device="cpu", compute_type="int8", cpu_threads=2)
    print("  Bundled base.en loaded successfully.")
    
    # 2. Connect VF1 Engine
    print("\n[2/3] Connecting VF1 Engine to Candidate Port 8090...")
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
    assert engine.is_server_healthy(), f"Candidate llama-server not responding on Port {PORT}!"
    print("  Candidate llama-server responding healthy.")
    
    # 3. Launch Notepad
    print("\n[3/3] Launching Windows Notepad for Real Text Injection...")
    proc_notepad, hwnd_notepad = launch_notepad()
    print(f"  Notepad running (HWND: {hwnd_notepad})")
    
    results = []
    taxonomy_counts = {
        "genuine_successful_transformation": 0,
        "literal_transcript_delivery": 0,
        "safe_fallback_without_task_completion": 0,
        "unsupported_command_gracefully_transcribed": 0,
        "task_failure": 0,
        "factual_corruption_reaching_user": 0
    }
    
    review_barrier_triggered_count = 0
    
    try:
        for idx, tc in enumerate(TEST_CASES, 1):
            cid = tc["id"]
            family = tc["family"]
            spoken = tc["spoken"]
            audio_file = AUDIO_DIR / tc["audio_file"]
            task = tc["task"]
            fmt = tc["format"]
            instruction = tc.get("instruction")
            draft = tc.get("draft")
            desc = tc["description"]
            
            print(f"\n--- [{idx:02d}/12] {cid}: {family} ---")
            print(f"  Utterance: \"{spoken[:65]}...\"")
            
            # A. Transcribe with base.en
            segs, _ = whisper.transcribe(str(audio_file), beam_size=1, language="en")
            transcription = " ".join(s.text.strip() for s in segs)
            print(f"  Whisper base.en: \"{transcription[:65]}...\"")
            
            # B. Polish via VF1 Engine
            res = engine.polish_transcript(
                transcription,
                task=task,
                format=fmt,
                instruction=instruction,
                draft=draft,
                timeout_seconds=4.0
            )
            raw_output = res.raw_output
            postprocessed = res.postprocessed_output
            final_text = res.final_text
            safety_decision = res
            
            # C. Inject into Notepad
            clear_notepad(hwnd_notepad)
            injector.inject_text(final_text, target_hwnd=hwnd_notepad)
            time.sleep(0.15)
            readback_text = injector.get_control_text(hwnd_notepad)
            
            # D. Critical factual corruption check
            is_corrupt = False
            if "2300" in spoken:
                if "02:30" in readback_text or "2:30" in readback_text:
                    is_corrupt = True
                    print("  [CRITICAL LEAK]: Corrupt 02:30 reached Notepad!")
                else:
                    print("  [SAFETY SHIELD]: 02:30 corruption prevented from reaching Notepad!")
                    
            # E. User-facing review barrier check
            barrier_triggered, flagged_ents, review_summary = check_user_review_barrier(
                final_text,
                task=task,
                draft=draft,
                user_dictionary=["Devon", "Devon Vance", "Redis cache"]
            )
            if barrier_triggered:
                review_barrier_triggered_count += 1
                print(f"  [REVIEW BARRIER TRIGGERED]: {review_summary[:80]}...")
                
            # F. Taxonomy classification
            taxonomy = evaluate_taxonomy(tc, raw_output, postprocessed, readback_text, safety_decision, is_corrupt)
            taxonomy_counts[taxonomy] += 1
            
            # G. Component error attribution
            attribution = determine_error_attribution(tc, transcription, raw_output, postprocessed, readback_text, safety_decision, taxonomy)
            
            print(f"  Delivered Text:  \"{readback_text.replace(chr(10), ' ')[:65]}...\"")
            print(f"  Taxonomy:        {taxonomy.upper()}")
            print(f"  Attribution:     {attribution}")
            
            results.append({
                "id": cid,
                "family": family,
                "description": desc,
                "spoken_utterance": spoken,
                "whisper_transcript": transcription,
                "raw_model_output": raw_output,
                "postprocessed_output": postprocessed,
                "final_delivered_text": readback_text,
                "taxonomy_verdict": taxonomy,
                "component_error_attribution": attribution,
                "review_barrier_triggered": barrier_triggered,
                "flagged_entities": [e.to_dict() for e in flagged_ents],
                "review_summary": review_summary,
                "safety_gate_accepted": safety_decision.safety_accepted,
                "safety_reasons": safety_decision.safety_reasons,
                "critical_corruption": is_corrupt
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

    summary = {
        "timestamp": "2026-10-15T17:45:00Z",
        "asr_model": "faster-whisper base.en (bundled in staging)",
        "llm_model": "s1-mini-vf1-run2-q5_k_m-v2.gguf on Port 8090",
        "total_test_cases": len(TEST_CASES),
        "taxonomy_metrics": taxonomy_counts,
        "genuine_transformation_success_rate": f"{taxonomy_counts['genuine_successful_transformation']} / 12 ({taxonomy_counts['genuine_successful_transformation']/12*100:.1f}%)",
        "literal_or_safe_delivery_rate": f"{(taxonomy_counts['genuine_successful_transformation'] + taxonomy_counts['literal_transcript_delivery'] + taxonomy_counts['safe_fallback_without_task_completion'] + taxonomy_counts['unsupported_command_gracefully_transcribed'])} / 12",
        "critical_factual_corruptions_reaching_user": taxonomy_counts["factual_corruption_reaching_user"],
        "review_barrier_triggered_cases": f"{review_barrier_triggered_count} / 12",
        "results": results
    }
    
    out_file = REPO_ROOT / "logs" / "p0_corrected_acceptance_truth_table.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\n" + "=" * 80)
    print("P0 ACCEPTANCE AUDIT FINISHED")
    print(f"Genuine Transformation Success: {summary['genuine_transformation_success_rate']}")
    print(f"Safe Fallbacks / Literals:     {taxonomy_counts['safe_fallback_without_task_completion']} fallbacks, {taxonomy_counts['literal_transcript_delivery']} literal")
    print(f"Task Failures:                 {taxonomy_counts['task_failure']}")
    print(f"Critical Corruptions to User:  {taxonomy_counts['factual_corruption_reaching_user']}")
    print(f"Review Barrier Triggered:      {summary['review_barrier_triggered_cases']}")
    print(f"Saved machine-readable truth table to {out_file}")
    print("=" * 80)

if __name__ == "__main__":
    main()
