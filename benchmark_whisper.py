"""Benchmark transcription speed of faster-whisper tiny.en vs google."""

import time
import numpy as np
from faster_whisper import WhisperModel

# Generate 5 seconds of mock audio (silence / noise)
sample_rate = 16000
duration = 5.0
dummy_audio = np.random.uniform(-0.05, 0.05, int(sample_rate * duration)).astype(np.float32)

print("Testing faster-whisper 'tiny.en' loading and inference speed...")
t0 = time.time()
model = WhisperModel("tiny.en", device="cpu", compute_type="int8", cpu_threads=4)
t_load = time.time() - t0
print(f"Model load time: {t_load:.2f}s")

t0 = time.time()
segments, _ = model.transcribe(dummy_audio, beam_size=1, vad_filter=True)
text = " ".join([s.text for s in segments])
t_infer = time.time() - t0
print(f"Inference time for {duration}s audio: {t_infer:.3f}s! ({duration/t_infer:.1f}x real-time speed)")
