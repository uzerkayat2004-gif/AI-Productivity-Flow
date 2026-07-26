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
    "contents": [{"parts": [{"text": "Clean this text: um hey there how are you"}]}],
    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 100}
}).encode("utf-8")

# Test 1: Standard new connection
t0 = time.time()
req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req) as resp:
    text = resp.read()
t_first = time.time() - t0
print(f"First request (with SSL handshake): {t_first:.3f}s")

# Test 2: Second request with opener pool / keep-alive
opener = urllib.request.build_opener()
t0 = time.time()
req2 = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "Connection": "keep-alive"})
with opener.open(req2) as resp2:
    text2 = resp2.read()
t_second = time.time() - t0
print(f"Second request (keep-alive): {t_second:.3f}s")
