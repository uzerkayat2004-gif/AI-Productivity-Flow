"""Quick speed test: record 4 seconds of audio and measure transcription time."""
import sys
import time
import logging
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", handlers=[logging.StreamHandler(sys.stdout)])

from voice_flow.audio import AudioRecorder
from voice_flow.transcriber import Transcriber

print()
print("=" * 50)
print("  Voice Flow - Ultra-Fast Speed Test")
print("=" * 50)
print()

t0 = time.time()
transcriber = Transcriber()
print(f"Model init time: {time.time() - t0:.2f}s")

print()
print(">>> Recording 4 seconds... SPEAK NOW! <<<")
print()

recorder = AudioRecorder()
recorder.start()
time.sleep(4)
audio = recorder.stop()

duration = len(audio) / 16000
max_amp = float(np.max(np.abs(audio))) if len(audio) > 0 else 0
print(f"Recorded: {len(audio)} samples ({duration:.1f}s, Max Amp: {max_amp:.4f})")

print("Transcribing...")
t_start = time.time()
text = transcriber.transcribe(audio)
elapsed = time.time() - t_start

print()
print(f"⚡ TRANSCRIPTION COMPLETED IN: {elapsed:.3f} SECONDS!")
if text:
    print(f"✅ SUCCESS! Transcribed text: '{text}'")
else:
    print("❌ No speech detected.")
