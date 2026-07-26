import time
import urllib.request
import json
import sqlite3
import os

db_path = os.path.join(os.path.expanduser("~"), ".voice_flow", "voice_flow.db")
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT api_key FROM provider_connections WHERE provider='gemini' AND is_active=1")
row = cur.fetchone()
key = row[0] if row else ""

models_to_test = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash-exp"]

for m in models_to_test:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": "Clean text: um hey there how are you doing today"}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 64}
    }).encode("utf-8")

    t0 = time.time()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            print(f"[{m}] SUCCESS ({time.time()-t0:.3f}s):", data["candidates"][0]["content"]["parts"][0]["text"].strip())
    except Exception as e:
        print(f"[{m}] FAILED ({time.time()-t0:.3f}s):", e)
