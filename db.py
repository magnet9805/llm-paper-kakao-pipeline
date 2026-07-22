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

CREATE TABLE IF NOT EXISTS keyword_groups (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('manual', 'llm_chat')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES keyword_groups(id) ON DELETE CASCADE,
    keyword_text TEXT NOT NULL
);
"""


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # keywords.group_id의 ON DELETE CASCADE는 SQLite에서 기본으로 꺼져 있어서
    # 켜줘야 실제로 동작한다 (연결마다 매번 켜야 함).
    conn.execute("PRAGMA foreign_keys = ON")
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
    """
    kakao_id가 이미 있으면 갱신, 없으면 새로 생성하고 users.id를 반환한다.

    "회원가입"이라는 별도 절차가 없는 이유: 카카오 로그인 자체가 곧 회원가입이기
    때문이다 (CLAUDE.md 설계 참고). 그래서 로그인할 때마다 이 함수 하나만 부르면
    되고, 처음 온 사람인지 아닌지는 kakao_id가 이미 DB에 있는지로만 판단한다.
    ON CONFLICT ... DO UPDATE (SQLite의 upsert 문법)가 그 "있으면 갱신, 없으면
    생성"을 한 번의 쿼리로 처리해준다.
    """
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


def create_keyword_group(
    user_id: int, title: str, keywords: list[str], source: str = "manual"
) -> dict:
    """
    키워드 그룹 하나(제목 + 키워드 목록)를 생성한다.
    group과 keywords, 두 테이블에 나눠 쓰는 작업이라 하나라도 실패하면 둘 다
    없었던 걸로 해야 하므로 같은 connection(=같은 트랜잭션) 안에서 처리한다.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO keyword_groups (user_id, title, source) VALUES (?, ?, ?)",
            (user_id, title, source),
        )
        group_id = cursor.lastrowid
        conn.executemany(
            "INSERT INTO keywords (group_id, keyword_text) VALUES (?, ?)",
            [(group_id, kw) for kw in keywords],
        )

    return {"id": group_id, "title": title, "source": source, "keywords": keywords}


def list_keyword_groups(user_id: int) -> list[dict]:
    """마이페이지에서 보여줄, 이 사용자의 키워드 그룹 전체를 키워드와 함께 반환한다."""
    with get_connection() as conn:
        groups = conn.execute(
            "SELECT id, title, source, created_at FROM keyword_groups "
            "WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()

        result = []
        for group in groups:
            keyword_rows = conn.execute(
                "SELECT keyword_text FROM keywords WHERE group_id = ?", (group["id"],)
            ).fetchall()
            result.append(
                {
                    "id": group["id"],
                    "title": group["title"],
                    "source": group["source"],
                    "created_at": group["created_at"],
                    "keywords": [row["keyword_text"] for row in keyword_rows],
                }
            )
        return result
