import urllib.request
import urllib.error

# Test 1: Without User-Agent
url = "https://api.groq.com/openai/v1/models"
req1 = urllib.request.Request(url, headers={"Authorization": "Bearer gsk_test12345"})
try:
    with urllib.request.urlopen(req1, timeout=5) as r:
        print("Req1 status:", r.status)
except urllib.error.HTTPError as e:
    print("Req1 HTTP Error:", e.code, e.reason)

# Test 2: With User-Agent
req2 = urllib.request.Request(url, headers={
    "Authorization": "Bearer gsk_test12345",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})
try:
    with urllib.request.urlopen(req2, timeout=5) as r:
        print("Req2 status:", r.status)
except urllib.error.HTTPError as e:
    print("Req2 HTTP Error:", e.code, e.reason)
