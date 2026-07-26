import sqlite3
import urllib.request
import json
import os

db_path = os.path.join(os.path.expanduser("~"), ".voice_flow", "voice_flow.db")
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT id, name, api_key FROM provider_connections WHERE provider='gemini' AND is_active=1")
rows = cur.fetchall()

prompt = (
    "You are an ultra-fast text polishing assistant. Clean up this spoken text by removing filler words ('um', 'uh', 'like', 'you know'), "
    "fixing punctuation/grammar, and capitalizing properly.\n"
    "CRITICAL INSTRUCTION: Output ONLY the final cleaned text. Do NOT add options, bullet points, intro text, quote marks, or explanation.\n\n"
    "Spoken text: um hello there how are you doing today actually I mean doing well"
)

for cid, cname, key in rows:
    print(f"Testing Gemini Key #{cid} ({cname})...")
    models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
    for m in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={key}"
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1}
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                print(f"  [SUCCESS] {m} -> Clean output: '{text}'")
                break
        except Exception as e:
            print(f"  [FAILED] {m} -> {e}")
