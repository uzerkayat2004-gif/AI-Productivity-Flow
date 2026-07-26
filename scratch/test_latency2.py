import time
import urllib.request
import json

# Test Groq vs Gemini latency with max_tokens=64
gemini_key = ""
db_path = r"C:\Users\Asus\.voice_flow\voice_flow.db"
import sqlite3
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT api_key FROM provider_connections WHERE provider='gemini' AND is_active=1")
row = cur.fetchone()
key = row[0] if row else ""

url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
payload = json.dumps({
    "contents": [{"parts": [{"text": "Clean text: um hey there how are you doing today"}]}],
    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 64}
}).encode("utf-8")

t0 = time.time()
req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode())
        print(f"Gemini 2.0 Flash ({time.time()-t0:.3f}s):", data["candidates"][0]["content"]["parts"][0]["text"].strip())
except Exception as e:
    print(f"Gemini 2.0 Flash failed ({time.time()-t0:.3f}s):", e)
