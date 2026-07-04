import sqlite3
import json
from typing import Dict, Any
from google.adk.tools import ToolContext, FunctionTool




USER_DB_FILE = "user_preferences.db"
# ... (code for setup_user_db, save_user_preferences, recall_user_preferences from previous answer) ...

def setup_user_db():
    with sqlite3.connect(USER_DB_FILE) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id TEXT NOT NULL, pref_key TEXT NOT NULL, pref_value TEXT NOT NULL,
            PRIMARY KEY (user_id, pref_key));""")
    print(f"✅ User preferences database '{USER_DB_FILE}' is ready.")

# TODO: implement save_user_preferences tools
def save_user_preferences(tool_context: ToolContext, new_preferences: Dict[str, Any]) -> str:
    user_id = tool_context.session.user_id
    with sqlite3.connect(USER_DB_FILE) as conn:
        for key, value in new_preferences.items():
            conn.execute("INSERT INTO user_preferences (user_id, pref_key, pref_value) VALUES (?, ?, ?) ON CONFLICT(user_id, pref_key) DO UPDATE SET pref_value = excluded.pref_value;",
                         (user_id, key, json.dumps(value)))
    return f"Preferences updated: {list(new_preferences.keys())}"

# TODO: implement recall_user_preferences tools

def recall_user_preferences(tool_context: ToolContext) -> Dict[str, Any]:
    user_id = tool_context.session.user_id
    preferences = {}
    with sqlite3.connect(USER_DB_FILE) as conn:
        rows = conn.execute("SELECT pref_key, pref_value FROM user_preferences WHERE user_id = ?", (user_id,)).fetchall()
        if not rows: return {"message": "No preferences found."}
        for key, value_str in rows: preferences[key] = json.loads(value_str)
    return preferences

# Tools to be imported by the agent
save_tool = FunctionTool(save_user_preferences)
recall_tool = FunctionTool(recall_user_preferences)