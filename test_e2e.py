"""Quick end-to-end test: record 4 seconds of audio and try to transcribe."""
import sys
import time
import logging
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", handlers=[logging.StreamHandler(sys.stdout)])

from voice_flow.audio import AudioRecorder
from voice_flow.transcriber import Transcriber

print()
print("=" * 50)
print("  Voice Flow - Speech Recognition Test")
print("=" * 50)
print()
print(">>> Recording 4 seconds... SPEAK NOW! <<<")
print()

recorder = AudioRecorder()
recorder.start()
time.sleep(4)
audio = recorder.stop()

duration = len(audio) / 16000
max_amp = float(np.max(np.abs(audio))) if len(audio) > 0 else 0
print(f"Recorded: {len(audio)} samples ({duration:.1f}s)")
print(f"Max amplitude: {max_amp:.4f}")

if max_amp < 0.01:
    print()
    print("WARNING: Very low audio level! Please speak louder or check mic volume.")
    sys.exit(1)

print()
print("Transcribing...")
transcriber = Transcriber()
text = transcriber.transcribe(audio)

print()
if text:
    print(f"✅ SUCCESS! Transcribed text: '{text}'")
else:
    print("❌ No speech detected. Try speaking clearly into your mic.")
