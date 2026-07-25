import speech_recognition as sr
import sounddevice as sd
import numpy as np
import wave
import tempfile
import os
import time

print("Recording 4 seconds... SPEAK NOW into your microphone!")
samplerate = 16000
duration = 4.0
audio = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype='int16')
sd.wait()

print("Recording complete. Max amplitude:", np.max(np.abs(audio)))

# Save to temporary WAV file
tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav")
os.close(tmp_fd)

try:
    with wave.open(tmp_path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(audio.tobytes())

    r = sr.Recognizer()
    with sr.AudioFile(tmp_path) as source:
        audio_data = r.record(source)
    
    print("Transcribing with SpeechRecognition engine...")
    text = r.recognize_google(audio_data)
    print("\nSUCCESS! Recognized text:", repr(text))

except Exception as e:
    print("\nError or no speech:", e)
finally:
    if os.path.exists(tmp_path):
        os.remove(tmp_path)
