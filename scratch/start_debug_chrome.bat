@echo off
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir="%USERPROFILE%\AppData\Local\Temp\chrome_debug_profile" "http://127.0.0.1:8991"
