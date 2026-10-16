import os
import sys
import wave
import numpy as np

sys.path.insert(0, os.path.abspath("src"))
os.environ["AI_PRODUCTIVITY_FLOW_ROOT"] = r"C:\Users\Asus\apf-release-build\staging"

from voice_flow.transcriber import Transcriber
from voice_flow.storage import storage
from voice_flow.dictionary import dictionary_engine

def load_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        data = wf.readframes(n_frames)
        if sampwidth == 2:
            audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        elif sampwidth == 4:
            audio = np.frombuffer(data, dtype=np.float32)
        else:
            raise ValueError(f"Unsupported sampwidth: {sampwidth}")
        if n_channels > 1:
            audio = audio[::n_channels]
        return audio, framerate

def main():
    print("--- Configuring Faster-Whisper base.en ---")
    storage.save_setting("voice_flow_stt_model", "local/faster-whisper-base.en")
    print("--- Checking Dictionary & Initial Prompt ---")
    prompt = dictionary_engine.get_initial_prompt()
    print("Initial prompt:", prompt[:100], "...")

    transcriber = Transcriber()
    print("Pre-warming Faster-Whisper base.en model...")
    transcriber._load_model_bg_impl("base.en")
    print("Faster-Whisper base.en model ready:", transcriber.model)
    case_ids = [f"ACCP-F{f}-{i:03d}" for f, i in [
        (1, 1), (1, 2),
        (2, 3), (2, 4), (2, 5),
        (3, 6),
        (4, 7),
        (5, 8),
        (6, 9),
        (7, 10), (7, 11),
        (8, 12),
    ]]

    wav_dir = r"C:\Users\Asus\AppData\Local\Temp\voice_flow_accp"
    results = {}

    for cid in case_ids:
        wav_path = os.path.join(wav_dir, f"{cid}.wav")
        if not os.path.exists(wav_path):
            print(f"Skipping {cid}: WAV not found at {wav_path}")
            continue
        audio, sr = load_wav(wav_path)
        transcript = transcriber.transcribe(audio, model_ref="local/faster-whisper-base.en")
        results[cid] = transcript
        print(f"[{cid}] -> {transcript}")

    return results

if __name__ == "__main__":
    main()
