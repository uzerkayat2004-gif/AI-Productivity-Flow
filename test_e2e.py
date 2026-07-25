"""Quick end-to-end test: record 3 seconds of audio and try to transcribe."""
import time
import numpy as np
from voice_flow.audio import AudioRecorder
from voice_flow.transcriber import Transcriber

print("Recording 3 seconds of audio... Speak now!")
recorder = AudioRecorder()
recorder.start()
time.sleep(3)
audio = recorder.stop()

print(f"Recorded {len(audio)} samples ({len(audio)/16000:.1f}s)")
print(f"Max amplitude: {np.max(np.abs(audio)):.4f}")

transcriber = Transcriber()
text = transcriber.transcribe(audio)

if text:
    print(f"SUCCESS: '{text}'")
else:
    print("No speech detected - check your microphone")
