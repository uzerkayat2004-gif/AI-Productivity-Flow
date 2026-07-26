import os
import sqlite3

db_path = os.path.expanduser("~/.voice_flow/voice_flow.db")
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    records = cursor.execute("SELECT id, app_name FROM history").fetchall()

    for rid, name in records:
        n_lower = name.lower()
        clean_name = name
        if "chrome" in n_lower:
            clean_name = "Google Chrome"
        elif "claude" in n_lower:
            clean_name = "Claude Code"
        elif "vscode" in n_lower or "visual studio code" in n_lower:
            clean_name = "VS Code"
        elif "slack" in n_lower:
            clean_name = "Slack"
        elif "whatsapp" in n_lower:
            clean_name = "WhatsApp"
        elif "notion" in n_lower:
            clean_name = "Notion"
        elif "explorer" in n_lower:
            clean_name = "File Explorer"
        elif " - " in name:
            clean_name = name.split(" - ")[-1]

        cursor.execute("UPDATE history SET app_name = ? WHERE id = ?", (clean_name, rid))

    conn.commit()
    conn.close()
    print("[OK] Migrated historical dictation app_name entries to clean application titles!")
