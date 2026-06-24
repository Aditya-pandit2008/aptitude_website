"""
Run this once from your backend/ folder to bring the DB schema up to date
with the current models.py, without losing any existing data.

Usage:
    cd backend
    python fix_db.py
"""
import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "instance", "database.db")

MIGRATIONS = [
    # questions: add missing columns
    "ALTER TABLE questions ADD COLUMN question_type TEXT DEFAULT 'mcq'",
    "ALTER TABLE questions ADD COLUMN created_by INTEGER",

    # code_challenges: add title + coding_attempts table
    "ALTER TABLE code_challenges ADD COLUMN title TEXT",

    # coding_attempts table (full create, safe if already exists)
    """CREATE TABLE IF NOT EXISTS coding_attempts (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id       INTEGER NOT NULL,
        challenge_id  INTEGER NOT NULL,
        language      TEXT,
        code          TEXT,
        status        TEXT,
        passed_cases  INTEGER DEFAULT 0,
        total_cases   INTEGER DEFAULT 0,
        ai_feedback   TEXT,
        score         REAL DEFAULT 0.0,
        xp_earned     INTEGER DEFAULT 0,
        created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id)      REFERENCES users(id),
        FOREIGN KEY (challenge_id) REFERENCES code_challenges(id)
    )""",

    # users: add total_xp if missing
    "ALTER TABLE users ADD COLUMN total_xp INTEGER DEFAULT 0",
]

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

for sql in MIGRATIONS:
    try:
        cur.execute(sql)
        print(f"OK: {sql[:60]}...")
    except sqlite3.OperationalError as e:
        # "duplicate column name" or "table already exists" → already applied
        print(f"SKIP ({e}): {sql[:60]}...")

conn.commit()
conn.close()
print("\nDone! DB schema is now up to date.")
