import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

from faster_whisper import WhisperModel
print("Loading tiny.en model...")
model = WhisperModel("tiny.en", device="cpu", compute_type="int8", cpu_threads=1, num_workers=1)

wav = os.path.expandvars(r"%TEMP%\voice_flow_accp\ACCP-F1-001.wav")
print(f"Transcribing {wav}...")
segments, info = model.transcribe(wav, beam_size=1, word_timestamps=False)
text = " ".join(s.text for s in segments).strip()
print("Transcribed text:", text)
