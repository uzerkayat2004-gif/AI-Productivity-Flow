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

url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
payload = json.dumps({
    "system_instruction": {
        "parts": [{"text": "You are Voice Flow AI text cleanup assistant. Output ONLY the polished final sentence without commentary or options."}]
    },
    "contents": [{"parts": [{"text": "Spoken text: um hey there how are you doing today"}]}],
    "generationConfig": {"temperature": 0.0, "maxOutputTokens": 100}
}).encode("utf-8")

t0 = time.time()
req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode())
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        print(f"Gemini 2.5 Flash System Instruction ({time.time()-t0:.3f}s): '{text}'")
except Exception as e:
    print(f"Failed ({time.time()-t0:.3f}s):", e)
