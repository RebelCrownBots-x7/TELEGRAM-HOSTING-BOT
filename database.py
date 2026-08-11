"""
REBEL CROWN BOT HOSTING - SQLite Database Module
"""

import sqlite3
import json
import time
import hashlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import contextmanager
from config import DATABASE_PATH, DEFAULT_SETTINGS, USERS_DIR

def get_connection():
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # DELETE journal is more reliable on Termux/Android shared storage than WAL
    try:
        conn.execute("PRAGMA journal_mode = DELETE")
    except Exception:
        pass
    try:
        conn.execute("PRAGMA synchronous = NORMAL")
    except Exception:
        pass
    return conn

@contextmanager
def db_session():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """Initialize all tables."""
    with db_session() as conn:
        c = conn.cursor()

        # Users
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                credits INTEGER DEFAULT 0,
                plan TEXT DEFAULT 'FREE',
                plan_expiry TEXT,
                free_hosting_used INTEGER DEFAULT 0,
                free_bots_used INTEGER DEFAULT 0,
                referral_code TEXT UNIQUE,
                referred_by INTEGER,
                referral_count INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                ban_reason TEXT,
                language TEXT DEFAULT 'en',
                created_at TEXT,
                updated_at TEXT,
                last_active TEXT
            )
        """)

        # Hosting requests (waiting for approval)
        c.execute("""
            CREATE TABLE IF NOT EXISTS hosting_requests (
                request_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                bot_id TEXT,
                filename TEXT,
                original_filename TEXT,
                file_path TEXT,
                bot_token_encrypted TEXT,
                status TEXT DEFAULT 'WAITING',
                admin_note TEXT,
                reject_reason TEXT,
                days_requested INTEGER DEFAULT 10,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Bots (approved & hosted)
        c.execute("""
            CREATE TABLE IF NOT EXISTS bots (
                bot_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                request_id TEXT,
                name TEXT,
                filename TEXT,
                file_path TEXT,
                bot_token_encrypted TEXT,
                status TEXT DEFAULT 'STOPPED',
                pid INTEGER,
                start_date TEXT,
                expiry_date TEXT,
                days INTEGER DEFAULT 10,
                auto_restart INTEGER DEFAULT 1,
                restart_count INTEGER DEFAULT 0,
                last_crash TEXT,
                created_at TEXT,
                updated_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Hosting history
        c.execute("""
            CREATE TABLE IF NOT EXISTS hosting_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id TEXT,
                user_id INTEGER,
                action TEXT,
                details TEXT,
                created_at TEXT
            )
        """)

        # Uploaded files metadata
        c.execute("""
            CREATE TABLE IF NOT EXISTS uploaded_files (
                file_id TEXT PRIMARY KEY,
                user_id INTEGER,
                request_id TEXT,
                bot_id TEXT,
                filename TEXT,
                original_filename TEXT,
                file_path TEXT,
                size INTEGER,
                status TEXT,
                uploaded_at TEXT
            )
        """)

        # Referrals
        c.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER UNIQUE,
                reward_given INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)

        # Credit transactions
        c.execute("""
            CREATE TABLE IF NOT EXISTS credit_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                balance_after INTEGER,
                type TEXT,
                description TEXT,
                admin_id INTEGER,
                created_at TEXT
            )
        """)

        # Redeem codes
        c.execute("""
            CREATE TABLE IF NOT EXISTS redeem_codes (
                code TEXT PRIMARY KEY,
                reward_type TEXT,
                reward_amount INTEGER,
                max_uses INTEGER DEFAULT 1,
                used_count INTEGER DEFAULT 0,
                per_user_limit INTEGER DEFAULT 1,
                expiry_date TEXT,
                is_active INTEGER DEFAULT 1,
                created_by INTEGER,
                created_at TEXT,
                note TEXT
            )
        """)

        # Redeem usage
        c.execute("""
            CREATE TABLE IF NOT EXISTS redeem_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                user_id INTEGER,
                created_at TEXT,
                UNIQUE(code, user_id)
            )
        """)

        # Support tickets
        c.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                ticket_id TEXT PRIMARY KEY,
                user_id INTEGER,
                subject TEXT,
                message TEXT,
                status TEXT DEFAULT 'OPEN',
                admin_reply TEXT,
                created_at TEXT,
                updated_at TEXT,
                closed_at TEXT
            )
        """)

        # Admin notes
        c.execute("""
            CREATE TABLE IF NOT EXISTS admin_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_type TEXT,
                target_id TEXT,
                note TEXT,
                admin_id INTEGER,
                created_at TEXT
            )
        """)

        # Settings (key-value)
        c.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )
        """)

        # Notifications / reminders sent
        c.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                bot_id TEXT,
                type TEXT,
                message TEXT,
                sent_at TEXT
            )
        """)

        # Process tracking
        c.execute("""
            CREATE TABLE IF NOT EXISTS processes (
                bot_id TEXT PRIMARY KEY,
                pid INTEGER,
                status TEXT,
                started_at TEXT,
                last_check TEXT,
                cpu_percent REAL,
                memory_mb REAL
            )
        """)

        # Logs (simple audit)
        c.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT,
                module TEXT,
                message TEXT,
                user_id INTEGER,
                created_at TEXT
            )
        """)

        # Admin audit log (Step 4)
        c.execute("""
            CREATE TABLE IF NOT EXISTS admin_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                action TEXT,
                target_type TEXT,
                target_id TEXT,
                description TEXT,
                created_at TEXT
            )
        """)

        # Indexes for common lookups (safe IF NOT EXISTS)
        for idx_sql in (
            "CREATE INDEX IF NOT EXISTS idx_bots_user ON bots(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_bots_status ON bots(status)",
            "CREATE INDEX IF NOT EXISTS idx_bots_expiry ON bots(expiry_date)",
            "CREATE INDEX IF NOT EXISTS idx_requests_status ON hosting_requests(status)",
            "CREATE INDEX IF NOT EXISTS idx_history_bot ON hosting_history(bot_id)",
            "CREATE INDEX IF NOT EXISTS idx_notif_user_type ON notifications(user_id, type)",
            "CREATE INDEX IF NOT EXISTS idx_logs_created ON logs(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_audit_admin ON admin_audit(admin_id)",
        ):
            try:
                c.execute(idx_sql)
            except Exception:
                pass

        # ── Migrations: add columns to existing tables if missing ──
        # (safe for fresh installs too — ALTER is skipped if the column already exists)
        _migrations = [
            ("hosting_requests", "file_type", "TEXT DEFAULT 'PY'"),
            ("hosting_requests", "entry_file", "TEXT"),
            ("bots", "file_type", "TEXT DEFAULT 'PY'"),
            ("bots", "entry_file", "TEXT"),
            ("uploaded_files", "file_type", "TEXT DEFAULT 'PY'"),
            # Step 3: daily bonus + ban timestamps
            ("users", "last_daily_claim", "TEXT"),
            ("users", "banned_at", "TEXT"),
            ("users", "unbanned_at", "TEXT"),
            # Step 4: monitoring fields on bots
            ("bots", "crash_count", "INTEGER DEFAULT 0"),
            ("bots", "last_error", "TEXT"),
            ("bots", "last_successful_start", "TEXT"),
            ("bots", "last_check", "TEXT"),
            ("bots", "manual_stop", "INTEGER DEFAULT 0"),
            # Step 4: reminder flags on bots
            ("bots", "reminder_3d_sent", "INTEGER DEFAULT 0"),
            ("bots", "reminder_1d_sent", "INTEGER DEFAULT 0"),
            ("bots", "reminder_expired_sent", "INTEGER DEFAULT 0"),
        ]
        for table, column, coltype in _migrations:
            try:
                existing = {row[1] for row in c.execute(f"PRAGMA table_info({table})").fetchall()}
                if column not in existing:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
            except Exception:
                pass

        # Insert default settings if missing
        now = datetime.utcnow().isoformat()
        for k, v in DEFAULT_SETTINGS.items():
            c.execute(
                "INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                (k, str(v), now)
            )
        # Step 3/4 defaults (never overwrite existing values)
        for k, v in {
            "daily_bonus_enabled": "1",
            "daily_bonus_min": "5",
            "daily_bonus_max": "1000",
            "daily_bonus_cooldown_hours": "24",
            # Step 4: crash protection
            "max_crash_restarts": "5",
            "crash_window_minutes": "30",
            "auto_restart": "1",
        }.items():
            c.execute(
                "INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                (k, str(v), now)
            )

    return True


# ─── Helpers ───

def now_iso():
    return datetime.utcnow().isoformat()

def generate_id(prefix: str = "") -> str:
    return f"{prefix}{secrets.token_hex(8)}"

def generate_referral_code(user_id: int) -> str:
    raw = f"{user_id}-{secrets.token_hex(4)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:10].upper()


# ─── Settings ───

def get_setting(key: str, default=None):
    with db_session() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row:
            return row["value"]
        return default if default is not None else DEFAULT_SETTINGS.get(key)

def set_setting(key: str, value):
    with db_session() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, str(value), now_iso())
        )

def get_all_settings() -> dict:
    with db_session() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


# ─── Users ───

def ensure_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None):
    with db_session() as conn:
        row = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)).fetchone()
        now = now_iso()
        if row:
            conn.execute(
                "UPDATE users SET username=?, first_name=?, last_name=?, last_active=?, updated_at=? WHERE user_id=?",
                (username, first_name, last_name, now, now, user_id)
            )
        else:
            ref_code = generate_referral_code(user_id)
            start_credits = int(get_setting("starting_credits", 0) or 0)
            conn.execute(
                """INSERT INTO users (user_id, username, first_name, last_name, credits,
                   referral_code, created_at, updated_at, last_active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, username, first_name, last_name, start_credits, ref_code, now, now, now)
            )
            # Create user storage dir
            (USERS_DIR / str(user_id) / "bots").mkdir(parents=True, exist_ok=True)
    return get_user(user_id)

def get_user(user_id: int):
    with db_session() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

def update_user(user_id: int, **kwargs):
    if not kwargs:
        return
    allowed = {"username", "first_name", "last_name", "credits", "plan", "plan_expiry",
               "free_hosting_used", "free_bots_used", "referral_count", "is_banned",
               "ban_reason", "referred_by", "updated_at", "last_active",
               "last_daily_claim", "banned_at", "unbanned_at"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    fields["updated_at"] = now_iso()
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [user_id]
    with db_session() as conn:
        conn.execute(f"UPDATE users SET {sets} WHERE user_id=?", vals)

def get_all_users(limit=500, offset=0):
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
        return [dict(r) for r in rows]

def count_users():
    with db_session() as conn:
        return conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]

def search_users(query: str, limit=50):
    q = f"%{query}%"
    with db_session() as conn:
        rows = conn.execute(
            """SELECT * FROM users WHERE CAST(user_id AS TEXT) LIKE ? OR username LIKE ?
               OR first_name LIKE ? LIMIT ?""",
            (q, q, q, limit)
        ).fetchall()
        return [dict(r) for r in rows]


# ─── Credits ───

def add_credits(user_id: int, amount: int, type_: str = "admin", description: str = "", admin_id: int = None):
    """Add (or remove if amount negative) credits. Balance never goes below 0."""
    with db_session() as conn:
        user = conn.execute("SELECT credits FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not user:
            return False
        new_bal = user["credits"] + amount
        if new_bal < 0:
            new_bal = 0
            amount = -user["credits"]  # actual delta applied
        conn.execute("UPDATE users SET credits=?, updated_at=? WHERE user_id=?",
                     (new_bal, now_iso(), user_id))
        conn.execute(
            """INSERT INTO credit_transactions (user_id, amount, balance_after, type, description, admin_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, amount, new_bal, type_, description, admin_id, now_iso())
        )
    return True

def remove_credits(user_id: int, amount: int, description: str = "", admin_id: int = None):
    """Remove credits (amount should be positive). Balance floors at 0."""
    if amount < 0:
        amount = abs(amount)
    return add_credits(user_id, -amount, type_="admin_remove", description=description or f"Admin removed {amount}", admin_id=admin_id)

def get_credit_history(user_id: int, limit=50):
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM credit_transactions WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]


# ─── Daily Bonus ───

def claim_daily_bonus(user_id: int):
    """
    Attempt to claim the daily bonus.
    Returns (ok: bool, message_or_amount).
    Bonus range and cooldown come from settings (defaults 5–1000, 24h).
    """
    import random
    enabled = get_setting("daily_bonus_enabled", "1") == "1"
    if not enabled:
        return False, "Daily bonus is currently disabled."

    min_c = int(get_setting("daily_bonus_min", 5) or 5)
    max_c = int(get_setting("daily_bonus_max", 1000) or 1000)
    if min_c < 0:
        min_c = 0
    if max_c < min_c:
        max_c = min_c
    cooldown_h = int(get_setting("daily_bonus_cooldown_hours", 24) or 24)

    with db_session() as conn:
        user = conn.execute(
            "SELECT credits, last_daily_claim FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        if not user:
            return False, "User not found."

        last = user["last_daily_claim"]
        if last:
            try:
                last_dt = datetime.fromisoformat(last)
                elapsed = datetime.utcnow() - last_dt
                if elapsed < timedelta(hours=cooldown_h):
                    remaining = timedelta(hours=cooldown_h) - elapsed
                    hrs = int(remaining.total_seconds() // 3600)
                    mins = int((remaining.total_seconds() % 3600) // 60)
                    return False, f"Cooldown active. Try again in {hrs}h {mins}m."
            except Exception:
                pass

        amount = random.randint(min_c, max_c)
        new_bal = (user["credits"] or 0) + amount
        now = now_iso()
        conn.execute(
            "UPDATE users SET credits=?, last_daily_claim=?, updated_at=? WHERE user_id=?",
            (new_bal, now, now, user_id)
        )
        conn.execute(
            """INSERT INTO credit_transactions
               (user_id, amount, balance_after, type, description, admin_id, created_at)
               VALUES (?, ?, ?, 'daily_bonus', ?, NULL, ?)""",
            (user_id, amount, new_bal, f"Daily bonus +{amount}", now)
        )
    return True, amount


# ─── Hosting Requests ───

def create_hosting_request(user_id: int, filename: str, original_filename: str, file_path: str,
                           bot_token_encrypted: str, days: int = 10,
                           file_type: str = "PY", entry_file: str = None) -> dict:
    request_id = generate_id("REQ")
    bot_id = generate_id("BOT")
    now = now_iso()
    # Size: for PY, file_path is the script itself; for ZIP, file_path is the
    # extracted project directory, so sum up the tree instead.
    fp = Path(file_path)
    if fp.is_dir():
        size = sum(f.stat().st_size for f in fp.rglob("*") if f.is_file())
    else:
        size = fp.stat().st_size if fp.exists() else 0
    with db_session() as conn:
        conn.execute(
            """INSERT INTO hosting_requests
               (request_id, user_id, bot_id, filename, original_filename, file_path,
                bot_token_encrypted, status, days_requested, created_at, updated_at,
                file_type, entry_file)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'WAITING', ?, ?, ?, ?, ?)""",
            (request_id, user_id, bot_id, filename, original_filename, file_path,
             bot_token_encrypted, days, now, now, file_type, entry_file)
        )
        conn.execute(
            """INSERT INTO uploaded_files
               (file_id, user_id, request_id, bot_id, filename, original_filename, file_path, size, status, uploaded_at, file_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'WAITING', ?, ?)""",
            (generate_id("FILE"), user_id, request_id, bot_id, filename, original_filename,
             file_path, size, now, file_type)
        )
    return get_request(request_id)

def get_request(request_id: str):
    with db_session() as conn:
        row = conn.execute("SELECT * FROM hosting_requests WHERE request_id=?", (request_id,)).fetchone()
        return dict(row) if row else None

def get_waiting_requests(limit=100):
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM hosting_requests WHERE status='WAITING' ORDER BY created_at ASC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

def update_request(request_id: str, **kwargs):
    allowed = {"status", "admin_note", "reject_reason", "days_requested", "updated_at"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    fields["updated_at"] = now_iso()
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [request_id]
    with db_session() as conn:
        conn.execute(f"UPDATE hosting_requests SET {sets} WHERE request_id=?", vals)

def update_uploaded_file_status(request_id: str, status: str):
    with db_session() as conn:
        conn.execute(
            "UPDATE uploaded_files SET status=? WHERE request_id=?",
            (status, request_id)
        )

def get_files(status: str = None, file_type: str = None, limit: int = 30):
    """File Manager listing — filter by status (WAITING/APPROVED/REJECTED) and/or type (PY/ZIP)."""
    query = "SELECT * FROM uploaded_files WHERE 1=1"
    params = []
    if status:
        query += " AND status=?"
        params.append(status)
    if file_type:
        query += " AND file_type=?"
        params.append(file_type)
    query += " ORDER BY uploaded_at DESC LIMIT ?"
    params.append(limit)
    with db_session() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

def get_file(file_id: str):
    with db_session() as conn:
        row = conn.execute("SELECT * FROM uploaded_files WHERE file_id=?", (file_id,)).fetchone()
        return dict(row) if row else None

def delete_file_record(file_id: str):
    with db_session() as conn:
        conn.execute("DELETE FROM uploaded_files WHERE file_id=?", (file_id,))

def get_user_requests(user_id: int):
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM hosting_requests WHERE user_id=? ORDER BY created_at DESC",
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ─── Bots ───

def create_bot_from_request(request: dict, days: int, start_now: bool = False) -> dict:
    now = now_iso()
    start = now
    expiry = (datetime.utcnow() + timedelta(days=days)).isoformat()
    with db_session() as conn:
        conn.execute(
            """INSERT INTO bots
               (bot_id, user_id, request_id, name, filename, file_path, bot_token_encrypted,
                status, start_date, expiry_date, days, created_at, updated_at,
                file_type, entry_file)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (request["bot_id"], request["user_id"], request["request_id"],
             request.get("original_filename") or request["filename"],
             request["filename"], request["file_path"], request["bot_token_encrypted"],
             "STOPPED", start, expiry, days, now, now,
             request.get("file_type") or "PY", request.get("entry_file"))
        )
        conn.execute(
            "UPDATE hosting_requests SET status='APPROVED', updated_at=? WHERE request_id=?",
            (now, request["request_id"])
        )
        conn.execute(
            """INSERT INTO hosting_history (bot_id, user_id, action, details, created_at)
               VALUES (?, ?, 'APPROVED', ?, ?)""",
            (request["bot_id"], request["user_id"], f"Approved for {days} days", now)
        )
    return get_bot(request["bot_id"])

def get_bot(bot_id: str):
    with db_session() as conn:
        row = conn.execute("SELECT * FROM bots WHERE bot_id=?", (bot_id,)).fetchone()
        return dict(row) if row else None

def get_user_bots(user_id: int):
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM bots WHERE user_id=? ORDER BY created_at DESC",
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]

def get_all_bots(limit=500):
    with db_session() as conn:
        rows = conn.execute("SELECT * FROM bots ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

def update_bot(bot_id: str, **kwargs):
    allowed = {
        "name", "status", "pid", "start_date", "expiry_date", "days",
        "auto_restart", "restart_count", "last_crash", "updated_at",
        "crash_count", "last_error", "last_successful_start", "last_check",
        "manual_stop", "reminder_3d_sent", "reminder_1d_sent", "reminder_expired_sent",
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    fields["updated_at"] = now_iso()
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [bot_id]
    with db_session() as conn:
        conn.execute(f"UPDATE bots SET {sets} WHERE bot_id=?", vals)

def add_hosting_history(bot_id: str, user_id: int, action: str, details: str = ""):
    """Record a hosting lifecycle event. Never raises."""
    try:
        with db_session() as conn:
            conn.execute(
                """INSERT INTO hosting_history (bot_id, user_id, action, details, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (bot_id, user_id, action, (details or "")[:1000], now_iso())
            )
    except Exception:
        pass

def get_hosting_history(bot_id: str = None, user_id: int = None, limit: int = 50):
    with db_session() as conn:
        if bot_id:
            rows = conn.execute(
                "SELECT * FROM hosting_history WHERE bot_id=? ORDER BY id DESC LIMIT ?",
                (bot_id, limit)
            ).fetchall()
        elif user_id:
            rows = conn.execute(
                "SELECT * FROM hosting_history WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (user_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM hosting_history ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

def count_bots_by_status(status: str = None):
    with db_session() as conn:
        if status:
            return conn.execute("SELECT COUNT(*) as c FROM bots WHERE status=?", (status,)).fetchone()["c"]
        return conn.execute("SELECT COUNT(*) as c FROM bots").fetchone()["c"]

def get_expired_bots():
    now = now_iso()
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM bots WHERE expiry_date < ? AND status NOT IN ('EXPIRED','DELETED')",
            (now,)
        ).fetchall()
        return [dict(r) for r in rows]

def get_running_bots():
    with db_session() as conn:
        rows = conn.execute("SELECT * FROM bots WHERE status='RUNNING'").fetchall()
        return [dict(r) for r in rows]

def get_bots_needing_reminder():
    """Bots that may need 3d / 1d / expired reminders (not DELETED)."""
    with db_session() as conn:
        rows = conn.execute(
            """SELECT * FROM bots
               WHERE status NOT IN ('DELETED')
                 AND expiry_date IS NOT NULL"""
        ).fetchall()
        return [dict(r) for r in rows]

def notification_already_sent(user_id: int, bot_id: str, ntype: str) -> bool:
    with db_session() as conn:
        row = conn.execute(
            "SELECT id FROM notifications WHERE user_id=? AND bot_id=? AND type=? LIMIT 1",
            (user_id, bot_id, ntype)
        ).fetchone()
        return bool(row)

def record_notification(user_id: int, bot_id: str, ntype: str, message: str = ""):
    try:
        with db_session() as conn:
            conn.execute(
                """INSERT INTO notifications (user_id, bot_id, type, message, sent_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, bot_id, ntype, (message or "")[:500], now_iso())
            )
    except Exception:
        pass

def log_admin_action(admin_id: int, action: str, target_type: str = "",
                     target_id: str = "", description: str = ""):
    """Audit log for admin actions. Never raises."""
    try:
        with db_session() as conn:
            conn.execute(
                """INSERT INTO admin_audit
                   (admin_id, action, target_type, target_id, description, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (admin_id, action, target_type, str(target_id or ""),
                 (description or "")[:1000], now_iso())
            )
        log_event("INFO", "audit", f"admin={admin_id} {action} {target_type}:{target_id} {description}")
    except Exception:
        pass

def get_admin_audit(limit: int = 50):
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM admin_audit ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


# ─── Redeem ───

def create_redeem_code(code: str, reward_type: str, reward_amount: int, max_uses: int = 1,
                       per_user_limit: int = 1, expiry_date: str = None, created_by: int = None,
                       note: str = None):
    with db_session() as conn:
        conn.execute(
            """INSERT INTO redeem_codes
               (code, reward_type, reward_amount, max_uses, per_user_limit, expiry_date,
                is_active, created_by, created_at, note)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
            (code.upper(), reward_type, reward_amount, max_uses, per_user_limit,
             expiry_date, created_by, now_iso(), note)
        )

def get_redeem_code(code: str):
    with db_session() as conn:
        row = conn.execute("SELECT * FROM redeem_codes WHERE code=?", (code.upper(),)).fetchone()
        return dict(row) if row else None

def use_redeem_code(code: str, user_id: int):
    code = code.upper()
    with db_session() as conn:
        rc = conn.execute("SELECT * FROM redeem_codes WHERE code=?", (code,)).fetchone()
        if not rc or not rc["is_active"]:
            return False, "Invalid or inactive code"
        if rc["expiry_date"] and rc["expiry_date"] < now_iso():
            return False, "Code has expired"
        if rc["used_count"] >= rc["max_uses"]:
            return False, "Code usage limit reached"
        used = conn.execute(
            "SELECT COUNT(*) as c FROM redeem_usage WHERE code=? AND user_id=?",
            (code, user_id)
        ).fetchone()["c"]
        if used >= rc["per_user_limit"]:
            return False, "You have already used this code"
        conn.execute(
            "INSERT INTO redeem_usage (code, user_id, created_at) VALUES (?, ?, ?)",
            (code, user_id, now_iso())
        )
        conn.execute(
            "UPDATE redeem_codes SET used_count = used_count + 1 WHERE code=?",
            (code,)
        )
        return True, dict(rc)

def get_all_redeem_codes(limit=100):
    with db_session() as conn:
        rows = conn.execute("SELECT * FROM redeem_codes ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


# ─── Support ───

def create_ticket(user_id: int, subject: str, message: str) -> str:
    ticket_id = generate_id("TKT")
    now = now_iso()
    with db_session() as conn:
        conn.execute(
            """INSERT INTO support_tickets
               (ticket_id, user_id, subject, message, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'OPEN', ?, ?)""",
            (ticket_id, user_id, subject, message, now, now)
        )
    return ticket_id

def get_ticket(ticket_id: str):
    with db_session() as conn:
        row = conn.execute("SELECT * FROM support_tickets WHERE ticket_id=?", (ticket_id,)).fetchone()
        return dict(row) if row else None

def get_open_tickets(limit=50):
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM support_tickets WHERE status='OPEN' ORDER BY created_at ASC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

def reply_ticket(ticket_id: str, reply: str):
    with db_session() as conn:
        conn.execute(
            "UPDATE support_tickets SET admin_reply=?, status='REPLIED', updated_at=? WHERE ticket_id=?",
            (reply, now_iso(), ticket_id)
        )


# ─── Referrals ───

def process_referral(referred_id: int, referrer_code: str) -> bool:
    with db_session() as conn:
        ref = conn.execute(
            "SELECT user_id FROM users WHERE referral_code=?", (referrer_code.upper(),)
        ).fetchone()
        if not ref:
            return False
        referrer_id = ref["user_id"]
        if referrer_id == referred_id:
            return False  # self-referral
        user = conn.execute("SELECT referred_by FROM users WHERE user_id=?", (referred_id,)).fetchone()
        if user and user["referred_by"]:
            return False  # already referred
        conn.execute(
            "UPDATE users SET referred_by=?, updated_at=? WHERE user_id=?",
            (referrer_id, now_iso(), referred_id)
        )
        conn.execute(
            "UPDATE users SET referral_count = referral_count + 1, updated_at=? WHERE user_id=?",
            (now_iso(), referrer_id)
        )
        conn.execute(
            "INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (?, ?, ?)",
            (referrer_id, referred_id, now_iso())
        )
        reward = int(get_setting("referral_reward_credits", 5) or 0)
        if reward > 0 and get_setting("referral_enabled", "1") == "1":
            # credit the referrer
            u = conn.execute("SELECT credits FROM users WHERE user_id=?", (referrer_id,)).fetchone()
            new_bal = u["credits"] + reward
            conn.execute("UPDATE users SET credits=? WHERE user_id=?", (new_bal, referrer_id))
            conn.execute(
                """INSERT INTO credit_transactions (user_id, amount, balance_after, type, description, created_at)
                   VALUES (?, ?, ?, 'referral', ?, ?)""",
                (referrer_id, reward, new_bal, f"Referral reward for user {referred_id}", now_iso())
            )
            conn.execute(
                "UPDATE referrals SET reward_given=1 WHERE referred_id=?",
                (referred_id,)
            )
        return True


# ─── Stats helpers ───

def get_dashboard_stats() -> dict:
    with db_session() as conn:
        total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
        banned = conn.execute("SELECT COUNT(*) as c FROM users WHERE is_banned=1").fetchone()["c"]
        # Active = last_active within 7 days
        cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()
        active_users = conn.execute(
            "SELECT COUNT(*) as c FROM users WHERE last_active >= ?", (cutoff,)
        ).fetchone()["c"]
        total_bots = conn.execute(
            "SELECT COUNT(*) as c FROM bots WHERE status!='DELETED'"
        ).fetchone()["c"]
        running = conn.execute("SELECT COUNT(*) as c FROM bots WHERE status='RUNNING'").fetchone()["c"]
        stopped = conn.execute("SELECT COUNT(*) as c FROM bots WHERE status='STOPPED'").fetchone()["c"]
        crashed = conn.execute("SELECT COUNT(*) as c FROM bots WHERE status='CRASHED'").fetchone()["c"]
        expired = conn.execute("SELECT COUNT(*) as c FROM bots WHERE status='EXPIRED'").fetchone()["c"]
        error_bots = conn.execute("SELECT COUNT(*) as c FROM bots WHERE status='ERROR'").fetchone()["c"]
        waiting = conn.execute("SELECT COUNT(*) as c FROM hosting_requests WHERE status='WAITING'").fetchone()["c"]
        approved = conn.execute("SELECT COUNT(*) as c FROM hosting_requests WHERE status='APPROVED'").fetchone()["c"]
        rejected = conn.execute("SELECT COUNT(*) as c FROM hosting_requests WHERE status='REJECTED'").fetchone()["c"]
        total_refs = conn.execute("SELECT COALESCE(SUM(referral_count),0) as c FROM users").fetchone()["c"]
        total_credits = conn.execute("SELECT COALESCE(SUM(credits),0) as c FROM users").fetchone()["c"]
        open_tickets = conn.execute("SELECT COUNT(*) as c FROM support_tickets WHERE status='OPEN'").fetchone()["c"]
        uploaded_files = conn.execute("SELECT COUNT(*) as c FROM uploaded_files").fetchone()["c"]
        redeem_usage = conn.execute("SELECT COUNT(*) as c FROM redeem_usage").fetchone()["c"]
        free_hosting_users = conn.execute(
            "SELECT COUNT(*) as c FROM users WHERE free_hosting_used=1"
        ).fetchone()["c"]
        # Expiring within 3 days, not already expired/deleted
        soon = (datetime.utcnow() + timedelta(days=3)).isoformat()
        now = now_iso()
        expiring_soon = conn.execute(
            """SELECT COUNT(*) as c FROM bots
               WHERE status NOT IN ('EXPIRED','DELETED')
                 AND expiry_date IS NOT NULL
                 AND expiry_date > ? AND expiry_date <= ?""",
            (now, soon)
        ).fetchone()["c"]
        active_hosting = conn.execute(
            "SELECT COUNT(*) as c FROM bots WHERE status IN ('RUNNING','STOPPED','CRASHED','ERROR','RESTARTING')"
        ).fetchone()["c"]
    return {
        "total_users": total_users,
        "active_users": active_users,
        "banned_users": banned,
        "total_bots": total_bots,
        "running_bots": running,
        "stopped_bots": stopped,
        "crashed_bots": crashed,
        "error_bots": error_bots,
        "expired_bots": expired,
        "waiting_requests": waiting,
        "approved_requests": approved,
        "rejected_requests": rejected,
        "active_hosting": active_hosting,
        "expiring_soon": expiring_soon,
        "uploaded_files": uploaded_files,
        "referral_count": total_refs,
        "total_credits": total_credits,
        "redeem_usage": redeem_usage,
        "free_hosting_users": free_hosting_users,
        "open_tickets": open_tickets,
    }


# ─── Logging ───

def log_event(level: str, module: str, message: str, user_id: int = None):
    try:
        with db_session() as conn:
            conn.execute(
                "INSERT INTO logs (level, module, message, user_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (level, module, message[:2000], user_id, now_iso())
            )
    except Exception:
        pass  # never break main flow for logging

def get_recent_logs(limit=100):
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
