"""Authentication and user session management for InterviewIQ.

Provides SQLite-based user registration, authentication, session tokens,
and test history tracking.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent / "interviewiq.db"
SESSION_DURATION_DAYS = 7


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize database tables for authentication and test history."""
    with _get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS test_history (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                assessment_id TEXT NOT NULL,
                category TEXT NOT NULL,
                language TEXT,
                difficulty TEXT,
                score INTEGER NOT NULL,
                feedback TEXT,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)
        conn.commit()


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Hash password using PBKDF2 with SHA-256 and salt."""
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    ).hex()
    return hashed, salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """Verify candidate password against stored hash."""
    hashed, _ = hash_password(password, salt)
    return secrets.compare_digest(hashed, stored_hash)


def register_user(name: str, email: str, password: str) -> dict[str, Any]:
    """Register a new candidate."""
    name = name.strip()
    email = email.strip().lower()
    if not name or len(name) < 2:
        raise ValueError("Name must be at least 2 characters.")
    if not email or "@" not in email or "." not in email:
        raise ValueError("Invalid email address format.")
    if not password or len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")

    init_db()
    user_id = secrets.token_hex(8)
    pw_hash, salt = hash_password(password)

    try:
        with _get_connection() as conn:
            conn.execute(
                "INSERT INTO users (id, name, email, password_hash, salt) VALUES (?, ?, ?, ?, ?)",
                (user_id, name, email, pw_hash, salt),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        raise ValueError("An account with this email already exists.")

    return {"id": user_id, "name": name, "email": email}


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    """Authenticate candidate and return user profile if credentials match."""
    init_db()
    email = email.strip().lower()
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, email, password_hash, salt FROM users WHERE email = ?",
            (email,),
        ).fetchone()

    if not row:
        return None
    if not verify_password(password, row["password_hash"], row["salt"]):
        return None

    return {"id": row["id"], "name": row["name"], "email": row["email"]}


def create_session(user_id: str) -> str:
    """Generate a session token for the user."""
    init_db()
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=SESSION_DURATION_DAYS)
    with _get_connection() as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires_at.isoformat()),
        )
        conn.commit()
    return token


def get_user_by_session(token: str | None) -> dict[str, Any] | None:
    """Retrieve candidate profile for a valid session token."""
    if not token:
        return None
    init_db()
    now = datetime.utcnow().isoformat()
    with _get_connection() as conn:
        row = conn.execute(
            """
            SELECT u.id, u.name, u.email
            FROM users u
            JOIN sessions s ON u.id = s.user_id
            WHERE s.token = ? AND s.expires_at > ?
            """,
            (token, now),
        ).fetchone()

    if not row:
        return None
    return {"id": row["id"], "name": row["name"], "email": row["email"]}


def delete_session(token: str) -> bool:
    """Log out candidate by removing the session."""
    init_db()
    with _get_connection() as conn:
        cursor = conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
        return cursor.rowcount > 0


def save_test_history(
    user_id: str,
    assessment_id: str,
    category: str,
    language: str | None,
    difficulty: str,
    score: int,
    feedback: str = "",
) -> None:
    """Persist completed test scorecard to user's dashboard history."""
    init_db()
    history_id = secrets.token_hex(8)
    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO test_history (id, user_id, assessment_id, category, language, difficulty, score, feedback)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (history_id, user_id, assessment_id, category, language, difficulty, score, feedback),
        )
        conn.commit()


def get_user_test_history(user_id: str) -> list[dict[str, Any]]:
    """Fetch past test assessments for candidate."""
    init_db()
    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, assessment_id, category, language, difficulty, score, feedback, completed_at
            FROM test_history
            WHERE user_id = ?
            ORDER BY completed_at DESC
            LIMIT 20
            """,
            (user_id,),
        ).fetchall()

    return [dict(row) for row in rows]
