import json
import os
import urllib.request

url = "http://127.0.0.1:9222/json/version"
try:
    with urllib.request.urlopen(url, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        ws_url = data.get("webSocketDebuggerUrl", "")
        # Extract path part e.g. /devtools/browser/...
        path = ws_url.replace("ws://127.0.0.1:9222", "").replace("ws://localhost:9222", "")
        
        target_dir = os.path.expanduser("~/AppData/Local/Google/Chrome/User Data")
        os.makedirs(target_dir, exist_ok=True)
        port_file = os.path.join(target_dir, "DevToolsActivePort")
        
        content = f"9222\n{path}\n"
        with open(port_file, "w", encoding="utf-8") as f:
            f.write(content)
            
        print(f"[OK] DevToolsActivePort file written successfully to {port_file}:\n{content}")
except Exception as e:
    print(f"[ERROR] Failed to fetch version or write DevToolsActivePort: {e}")
