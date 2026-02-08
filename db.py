import sqlite3
from pathlib import Path

DB_PATH = Path("app.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts DATETIME DEFAULT CURRENT_TIMESTAMP,
        chat_id TEXT,
        username TEXT,
        text TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        chat_id TEXT NOT NULL,
        text TEXT NOT NULL,
        cron TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1
    )
    """)

    # memory: lưu hội thoại gần đây để bot trả lời “có ngữ cảnh”
    cur.execute("""
    CREATE TABLE IF NOT EXISTS convo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts DATETIME DEFAULT CURRENT_TIMESTAMP,
        chat_id TEXT NOT NULL,
        role TEXT NOT NULL,   -- 'user' or 'bot'
        text TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()

def set_setting(key: str, value: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()

def get_setting(key: str):
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else None

def add_message(chat_id: str, username: str, text: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO messages(chat_id,username,text) VALUES(?,?,?)",
        (str(chat_id), username or "", text or ""),
    )
    conn.commit()
    conn.close()

def list_messages(limit=200):
    conn = get_conn()
    rows = conn.execute(
        "SELECT ts, chat_id, username, text FROM messages ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return rows

def create_schedule(name: str, chat_id: str, text: str, cron: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO schedules(name,chat_id,text,cron,enabled) VALUES(?,?,?,?,1)",
        (name, str(chat_id), text, cron),
    )
    conn.commit()
    conn.close()

def list_schedules():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id,name,chat_id,text,cron,enabled FROM schedules ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return rows

def set_schedule_enabled(schedule_id: int, enabled: bool):
    conn = get_conn()
    conn.execute(
        "UPDATE schedules SET enabled=? WHERE id=?",
        (1 if enabled else 0, schedule_id),
    )
    conn.commit()
    conn.close()

def delete_schedule(schedule_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))
    conn.commit()
    conn.close()

# ===== convo memory =====
def add_convo(chat_id: str, role: str, text: str, keep: int = 120):
    conn = get_conn()
    conn.execute(
        "INSERT INTO convo(chat_id,role,text) VALUES(?,?,?)",
        (str(chat_id), role, text),
    )
    # giữ tối đa keep dòng / chat để DB nhẹ
    conn.execute("""
        DELETE FROM convo
        WHERE id IN (
            SELECT id FROM convo
            WHERE chat_id=?
            ORDER BY id DESC
            LIMIT -1 OFFSET ?
        )
    """, (str(chat_id), keep))
    conn.commit()
    conn.close()

def get_recent_convo(chat_id: str, limit: int = 14):
    conn = get_conn()
    rows = conn.execute(
        "SELECT role,text FROM convo WHERE chat_id=? ORDER BY id DESC LIMIT ?",
        (str(chat_id), limit),
    ).fetchall()
    conn.close()
    return list(reversed(rows))