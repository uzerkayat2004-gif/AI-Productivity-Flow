import time
import os
import numpy as np
from faster_whisper import WhisperModel

# Generate 15 seconds of dummy speech audio (16kHz)
sample_rate = 16000
duration = 15.0
t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)
# 440Hz tone simulating speech wave
audio = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

print("=== BENCHMARKING WHISPER STT LATENCY ON CPU ===")

# Test 1: base.en with 12 threads
t0 = time.time()
m_base12 = WhisperModel("base.en", device="cpu", compute_type="int8", cpu_threads=12)
t_load1 = time.time() - t0

t0 = time.time()
seg1, _ = m_base12.transcribe(audio, beam_size=1, vad_filter=False)
list(seg1)
t_stt1 = time.time() - t0
print(f"1. base.en (12 threads): Load={t_load1:.2f}s | STT 15s audio={t_stt1:.3f}s")

# Test 2: base.en with 4 physical threads
t0 = time.time()
m_base4 = WhisperModel("base.en", device="cpu", compute_type="int8", cpu_threads=4)
t_stt2_load = time.time() - t0

t0 = time.time()
seg2, _ = m_base4.transcribe(audio, beam_size=1, vad_filter=False)
list(seg2)
t_stt2 = time.time() - t0
print(f"2. base.en (4 physical threads): Load={t_stt2_load:.2f}s | STT 15s audio={t_stt2:.3f}s")

# Test 3: tiny.en with 4 physical threads
t0 = time.time()
m_tiny4 = WhisperModel("tiny.en", device="cpu", compute_type="int8", cpu_threads=4)
t_stt3_load = time.time() - t0

t0 = time.time()
seg3, _ = m_tiny4.transcribe(audio, beam_size=1, vad_filter=False)
list(seg3)
t_stt3 = time.time() - t0
print(f"3. tiny.en (4 physical threads): Load={t_stt3_load:.2f}s | STT 15s audio={t_stt3:.3f}s")
