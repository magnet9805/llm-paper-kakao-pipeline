"""
SQLite 기반 사용자 저장소. 카카오 소셜 로그인이 곧 회원가입이라 password 필드는 없고,
카카오 access/refresh token도 users 테이블에 같이 저장한다.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_PATH = "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    kakao_id TEXT UNIQUE NOT NULL,
    nickname TEXT,
    profile_image_url TEXT,
    kakao_access_token TEXT NOT NULL,
    kakao_refresh_token TEXT NOT NULL,
    kakao_token_expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(SCHEMA)


def upsert_user(
    kakao_id: str,
    nickname: str | None,
    profile_image_url: str | None,
    access_token: str,
    refresh_token: str,
    expires_at: datetime,
) -> int:
    """kakao_id가 이미 있으면 갱신, 없으면 새로 생성하고 users.id를 반환한다."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (kakao_id, nickname, profile_image_url,
                                kakao_access_token, kakao_refresh_token, kakao_token_expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(kakao_id) DO UPDATE SET
                nickname = excluded.nickname,
                profile_image_url = excluded.profile_image_url,
                kakao_access_token = excluded.kakao_access_token,
                kakao_refresh_token = excluded.kakao_refresh_token,
                kakao_token_expires_at = excluded.kakao_token_expires_at
            """,
            (kakao_id, nickname, profile_image_url, access_token, refresh_token, expires_at),
        )
        row = conn.execute("SELECT id FROM users WHERE kakao_id = ?", (kakao_id,)).fetchone()
        return row["id"]


def get_user(user_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
