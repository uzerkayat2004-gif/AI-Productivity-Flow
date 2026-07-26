import json
import sys
import urllib.request

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "http://127.0.0.1:8991"

def api_get(endpoint):
    url = f"{BASE_URL}{endpoint}"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))

def api_post(endpoint, payload):
    url = f"{BASE_URL}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

print("=== VOICE FLOW LIVE UI INTERACTION ===")

# 1. Fetch History
history = api_get("/api/history")
print(f"1. History Records Count: {len(history)}")

# 2. Fetch Dictionary & Add Term
dict_words = api_get("/api/dictionary")
print(f"2. Initial Dictionary Words ({len(dict_words)}): {dict_words[:5]}")

add_res = api_post("/api/dictionary/add", {"word": "WhisperFlow"})
print(f"   Added 'WhisperFlow' to Dictionary -> Success: {add_res.get('success')}")

# 3. Fetch Style Presets
styles = api_get("/api/styles/get")
print(f"3. Active Style Presets: {styles}")

# 4. Fetch Insights
insights = api_get("/api/insights")
print(f"4. User Insights Statistics: {insights}")

print("=== UI INTERACTION COMPLETED SUCCESSFULLY ===")
