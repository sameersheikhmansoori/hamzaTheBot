"""
Database management module for Telegram Link Distributor Bot.
Uses SQLite for persistent and portable data storage.
"""

import sqlite3
import os
from contextlib import contextmanager
from typing import List, Dict, Optional, Any

DB_PATH = os.getenv("DB_PATH", "bot.db")


@contextmanager
def get_connection(db_path: Optional[str] = None):
    target_path = db_path if db_path is not None else DB_PATH
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path: Optional[str] = None) -> None:
    """Initialize database tables."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Table for storing options and their respective links
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                description TEXT DEFAULT '',
                clicks INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Table for storing registered users
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Table for logging link accesses
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS access_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                option_id INTEGER NOT NULL,
                accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (option_id) REFERENCES options(id) ON DELETE CASCADE
            )
        """)

        # Table for bot settings (e.g. approval mode)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # Default setting for version 1.0: Approval mode is ON by default
        cursor.execute("SELECT 1 FROM settings WHERE key = 'require_approval'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO settings (key, value) VALUES ('require_approval', '1')")

        # Table for user link requests
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS link_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                option_id INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (option_id) REFERENCES options(id) ON DELETE CASCADE
            )
        """)

        # Table for group member warnings
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                warn_count INTEGER DEFAULT 0,
                last_warned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, user_id)
            )
        """)
        conn.commit()


def add_option(title: str, url: str, description: str = "", db_path: Optional[str] = None) -> int:
    """Add a new option with its link."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO options (title, url, description) VALUES (?, ?, ?)",
            (title.strip(), url.strip(), description.strip())
        )
        conn.commit()
        return cursor.lastrowid


def get_options(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve all options sorted by creation date."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, url, description, clicks, created_at FROM options ORDER BY id ASC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_option(option_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve a single option by ID."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, url, description, clicks, created_at FROM options WHERE id = ?", (option_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def delete_option(option_id: int, db_path: Optional[str] = None) -> bool:
    """Delete an option by ID."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM options WHERE id = ?", (option_id,))
        conn.commit()
        return cursor.rowcount > 0


def record_click(user_id: int, option_id: int, db_path: Optional[str] = None) -> None:
    """Increment click count and record in access logs."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE options SET clicks = clicks + 1 WHERE id = ?", (option_id,))
        cursor.execute("INSERT INTO access_logs (user_id, option_id) VALUES (?, ?)", (user_id, option_id))
        conn.commit()


def register_user(user_id: int, username: Optional[str], first_name: Optional[str], last_name: Optional[str], db_path: Optional[str] = None) -> None:
    """Save or update a Telegram user."""
    u_str = str(username) if username is not None else ""
    f_str = str(first_name) if first_name is not None else ""
    l_str = str(last_name) if last_name is not None else ""

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                last_name=excluded.last_name
        """, (user_id, u_str, f_str, l_str))
        conn.commit()


def get_user(user_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve stored user details by ID."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, first_name, last_name, first_seen FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_stats(db_path: Optional[str] = None) -> Dict[str, int]:
    """Retrieve summary statistics."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM options")
        total_options = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COALESCE(SUM(clicks), 0) FROM options")
        total_clicks = cursor.fetchone()[0]
        
        return {
            "total_options": total_options,
            "total_users": total_users,
            "total_clicks": total_clicks
        }


def get_setting(key: str, default: str = "", db_path: Optional[str] = None) -> str:
    """Get a configuration setting value."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default


def set_setting(key: str, value: str, db_path: Optional[str] = None) -> None:
    """Set or update a configuration setting."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
        conn.commit()


def is_approval_required(db_path: Optional[str] = None) -> bool:
    """Check if links require admin approval before delivery (default ON in v1.0)."""
    return get_setting("require_approval", "1", db_path) == "1"


def toggle_approval_mode(db_path: Optional[str] = None) -> bool:
    """Toggle approval mode ON / OFF and return the new state."""
    new_state = not is_approval_required(db_path)
    set_setting("require_approval", "1" if new_state else "0", db_path)
    return new_state


def create_link_request(user_id: int, username: Optional[str], first_name: Optional[str], option_id: int, db_path: Optional[str] = None) -> int:
    """Create a new pending link request."""
    u_str = str(username) if username is not None else ""
    f_str = str(first_name) if first_name is not None else ""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO link_requests (user_id, username, first_name, option_id, status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (user_id, username or "", first_name or "", option_id))
        conn.commit()
        return cursor.lastrowid


def get_link_request(request_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetch details of a link request."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.id, r.user_id, r.username, r.first_name, r.option_id, r.status, r.created_at,
                   o.title as option_title, o.url as option_url
            FROM link_requests r
            LEFT JOIN options o ON r.option_id = o.id
            WHERE r.id = ?
        """, (request_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_request_status(request_id: int, status: str, db_path: Optional[str] = None) -> bool:
    """Update status of a link request ('approved', 'rejected')."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE link_requests SET status = ? WHERE id = ?", (status, request_id))
        conn.commit()
        return cursor.rowcount > 0


def add_warning(chat_id: int, user_id: int, db_path: Optional[str] = None) -> int:
    """Increment warning count for a user in a chat and return the new count."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO warnings (chat_id, user_id, warn_count, last_warned_at)
            VALUES (?, ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                warn_count = warn_count + 1,
                last_warned_at = CURRENT_TIMESTAMP
        """, (chat_id, user_id))
        cursor.execute("SELECT warn_count FROM warnings WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        row = cursor.fetchone()
        conn.commit()
        return row[0] if row else 1


def get_warnings(chat_id: int, user_id: int, db_path: Optional[str] = None) -> int:
    """Get current warning count for a user in a chat."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT warn_count FROM warnings WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        row = cursor.fetchone()
        return row[0] if row else 0


def remove_warning(chat_id: int, user_id: int, db_path: Optional[str] = None) -> int:
    """Decrement warning count for a user (minimum 0)."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE warnings
            SET warn_count = CASE WHEN warn_count > 0 THEN warn_count - 1 ELSE 0 END,
                last_warned_at = CURRENT_TIMESTAMP
            WHERE chat_id = ? AND user_id = ?
        """, (chat_id, user_id))
        cursor.execute("SELECT warn_count FROM warnings WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        row = cursor.fetchone()
        conn.commit()
        return row[0] if row else 0


def reset_warnings(chat_id: int, user_id: int, db_path: Optional[str] = None) -> None:
    """Reset warnings for a user in a chat."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM warnings WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        conn.commit()

