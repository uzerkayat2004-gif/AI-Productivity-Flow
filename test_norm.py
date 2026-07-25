"""Test base.en model with audio volume normalization for distant/quiet speech."""

import time
import numpy as np
from faster_whisper import WhisperModel

print("Loading 'base.en' model...")
t0 = time.time()
model = WhisperModel("base.en", device="cpu", compute_type="int8", cpu_threads=4)
print(f"Model loaded in {time.time() - t0:.2f}s")

# Test audio normalization function
def normalize_audio(audio: np.ndarray) -> np.ndarray:
    max_amp = np.max(np.abs(audio))
    if max_amp > 0.001:
        # Scale audio so peak amplitude is 0.95 (standard broadcast volume)
        return (audio / max_amp * 0.95).astype(np.float32)
    return audio

# Test with 5s mock audio
dummy = np.random.uniform(-0.02, 0.02, 16000 * 5).astype(np.float32)
norm_dummy = normalize_audio(dummy)

t0 = time.time()
segments, _ = model.transcribe(
    norm_dummy,
    beam_size=3,
    language="en",
    initial_prompt="Hello, this is clear English speech dictation.",
    vad_filter=True,
)
t_infer = time.time() - t0
print(f"Inference time for 5s audio on base.en: {t_infer:.3f}s")
