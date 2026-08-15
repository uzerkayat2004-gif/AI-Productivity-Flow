"""End-to-end verification of the BACKEND dictionary pipeline.
Uses an isolated temp DB and a fake Whisper model; everything else is the real production code.
"""
import os
import sys
import tempfile
import threading
import numpy as np

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from voice_flow.storage import storage
from voice_flow.dictionary import dictionary_engine
from voice_flow.transcriber import Transcriber
from voice_flow.polisher import polisher

TMP = tempfile.mkdtemp(prefix="vf_dict_e2e_")
storage.db_path = os.path.join(TMP, "voice_flow.db")
storage._init_db()

PASS = 0
FAIL = 0

def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name} {extra}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {extra}")

print("=== STAGE 1: dictionary boot/load + revision refresh ===")
storage.add_dictionary_word("voice flow -> VoiceFlow")
storage.add_dictionary_word("my path -> C:\\Users\\me\\file.txt")
dictionary_engine.mark_dirty()
words = dictionary_engine.refresh_words()
check("engine loads both terms from DB", set(words) == {"voice flow -> VoiceFlow", "my path -> C:\\Users\\me\\file.txt"}, words)
prompt = dictionary_engine.get_initial_prompt()
check("Whisper bias prompt includes VoiceFlow trigger", "voice flow" in prompt, repr(prompt))
check("no stopwords / short junk in prompt", " and " not in prompt and " the " not in prompt and " a " not in prompt, repr(prompt))
print("  prompt:", prompt)

print("\n=== STAGE 2: transcription with dictionary prompt biasing (fake model) ===")
class Segment:
    def __init__(self, text):
        self.text = text

class FakeModel:
    def __init__(self):
        self.calls = []
        self.fail_vad_first = True
    def transcribe(self, audio, **kw):
        self.calls.append(kw)
        if kw.get("vad_filter") and self.fail_vad_first:
            self.fail_vad_first = False
            raise RuntimeError("simulated VAD failure")
        return iter([Segment("we use voice flow daily")]), None

t = Transcriber.__new__(Transcriber)
t.model = FakeModel()
t._transcribe_lock = threading.Lock()

audio = np.ones(32000, dtype=np.float32) * 0.5  # 2s @ 16kHz
result = t.transcribe(audio)
calls = t.model.calls
check("VAD pass ran first with vad_filter=True", len(calls) >= 1 and calls[0].get("vad_filter") is True)
check("initial_prompt passed to Whisper (bias active)", calls and "voice flow" in (calls[0].get("initial_prompt") or ""))
check("VAD failure fell back to direct pass", len(calls) >= 2 and calls[1].get("vad_filter") is False)
check("transcribe returned text", result == "we use voice flow daily", repr(result))

storage.add_dictionary_word("HyperKube")
dictionary_engine.mark_dirty()
result2 = t.transcribe(audio)
prompt2 = t.model.calls[-1].get("initial_prompt") or ""
check("new term picked up WITHOUT restart (revision refresh)", "HyperKube" in prompt2, repr(prompt2))

print("\n=== STAGE 3: polish pipeline applies dictionary post-processing ===")
out1 = polisher.polish("we use voice flow daily", "smart_clean")
check("snippet casing fix: 'voice flow' -> VoiceFlow", out1 == "We use VoiceFlow daily.", repr(out1))
out2 = polisher.polish("open my path now", "smart_clean")
check("snippet expansion: my path -> C:\\Users\\me\\file.txt", out2 == r"Open C:\Users\me\file.txt now.", repr(out2))
out3 = polisher.polish("voice flow ready", "smart_clean")
check("ultra-short path (<=3 words) still applies dictionary", out3 == "VoiceFlow ready.", repr(out3))
out4 = polisher.polish("voice flow voice flow", "smart_clean")
check("idempotent across dictations (no cascade)", out4 == "VoiceFlow VoiceFlow.", repr(out4))
url_safe = polisher.polish("visit voice flow at https://example.com/voiceflow", "smart_clean")
check("URLs protected from dictionary rewrite", "https://example.com/voiceflow" in url_safe, repr(url_safe))

print("\n=== STAGE 4: storage -> history + insights aggregation ===")
rec = storage.add_dictation(
    raw_text="we use voice flow daily for our voiceflow reports",
    polished_text=out1,
    app_name="Notepad",
    duration_sec=3.0,
    style_mode="smart_clean",
)
check("history record persisted", rec.id is not None and rec.id > 0, f"id={rec.id}")
check("word count computed (voice flow -> VoiceFlow merges tokens)", rec.word_count == 4, f"wc={rec.word_count}")
hist = storage.get_recent_history(10)
check("history retrievable", len(hist) >= 1 and hist[0]["polished_text"] == out1)

ins = storage.get_insights("all")
check("insights computed", ins is not None and isinstance(ins, dict))
check("dictionary term counted in insights", ins.get("total_dictionary_terms") == 3, f"terms={ins.get('total_dictionary_terms')}")
check("auto-learning disabled by default (no Auto-Captured rows)",
      all(r["category"] != "Auto-Captured" for r in storage.get_dictionary_entries(include_auto=True)))

print("\n=== STAGE 5: dictionary API contract (storage layer) ===")
ok1 = storage.add_dictionary_word("   ")
check("empty word rejected", ok1 is False)
ok2 = storage.remove_dictionary_word("does-not-exist")
check("missing word remove returns False", ok2 is False)
rev_before = storage.get_dictionary_revision()
storage.add_dictionary_word("UniqueTermX")
rev_after = storage.get_dictionary_revision()
check("revision bumps on add (drives lazy reload)", rev_after is not None and rev_after != rev_before, f"{rev_before} -> {rev_after}")

print(f"\n========== RESULT: {PASS} passed, {FAIL} failed ==========")
print("temp db:", TMP)
sys.exit(1 if FAIL else 0)