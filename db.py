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
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES keyword_groups(id) ON DELETE CASCADE,
    keyword_text TEXT NOT NULL
);

-- 사용자마다 "이미 보낸 논문"이 달라야 하므로(개인용 스크립트의 전역 seen_papers.json과
-- 달리) 사용자별로 발송 이력을 남긴다. UNIQUE(user_id, hf_id)로 같은 논문을 같은
-- 사용자에게 중복 저장하는 걸 막는다.
CREATE TABLE IF NOT EXISTS sent_papers (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    hf_id TEXT NOT NULL,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, hf_id)
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
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """
    CREATE TABLE IF NOT EXISTS는 이미 만들어진 테이블에 새 컬럼을 추가해주지 않는다.
    is_active 컬럼(그룹별 발송 on/off) 도입 이전에 만들어진 기존 app.db를 위한
    1회성 보정 - 이미 컬럼이 있으면 아무 것도 하지 않는다.
    """
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(keyword_groups)").fetchall()}
    if "is_active" not in columns:
        conn.execute("ALTER TABLE keyword_groups ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")


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

        saved_keywords = []
        for kw in keywords:
            kw_cursor = conn.execute(
                "INSERT INTO keywords (group_id, keyword_text) VALUES (?, ?)", (group_id, kw)
            )
            saved_keywords.append({"id": kw_cursor.lastrowid, "text": kw})

    return {
        "id": group_id,
        "title": title,
        "source": source,
        "is_active": True,
        "keywords": saved_keywords,
    }


def list_keyword_groups(user_id: int) -> list[dict]:
    """
    마이페이지에서 보여줄, 이 사용자의 키워드 그룹 전체를 키워드와 함께 반환한다.
    keywords는 문자열이 아니라 {id, text} 형태로 반환한다 - 화면에서 키워드 하나를
    개별 삭제하려면 그 키워드의 고유 id가 있어야 하기 때문이다.
    """
    with get_connection() as conn:
        groups = conn.execute(
            "SELECT id, title, source, is_active, created_at FROM keyword_groups "
            "WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()

        result = []
        for group in groups:
            keyword_rows = conn.execute(
                "SELECT id, keyword_text FROM keywords WHERE group_id = ?", (group["id"],)
            ).fetchall()
            result.append(
                {
                    "id": group["id"],
                    "title": group["title"],
                    "source": group["source"],
                    "is_active": bool(group["is_active"]),
                    "created_at": group["created_at"],
                    "keywords": [
                        {"id": row["id"], "text": row["keyword_text"]} for row in keyword_rows
                    ],
                }
            )
        return result


def set_keyword_group_active(user_id: int, group_id: int, is_active: bool) -> bool:
    """
    그룹별 발송 on/off. 키워드로 등록은 해뒀지만 오늘은 다른 관심 그룹의 논문만
    받고 싶은 경우를 위한 기능 - 꺼둔 그룹은 /api/send-now의 클러스터 구성에서
    제외된다 (그룹/키워드 자체는 그대로 남아있고, 발송 대상에서만 빠진다).
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE keyword_groups SET is_active = ? WHERE id = ? AND user_id = ?",
            (1 if is_active else 0, group_id, user_id),
        )
        return cursor.rowcount > 0


def update_keyword_group_title(user_id: int, group_id: int, title: str) -> bool:
    """
    그룹 제목을 수정한다. WHERE 절에 user_id도 같이 넣어서, 남의 그룹 id를 넣어도
    수정되지 않도록 막는다 (소유권 확인). 실제로 수정된 행이 있었으면 True.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE keyword_groups SET title = ? WHERE id = ? AND user_id = ?",
            (title, group_id, user_id),
        )
        return cursor.rowcount > 0


def delete_keyword_group(user_id: int, group_id: int) -> bool:
    """그룹을 통째로 삭제한다. 소속 keywords는 ON DELETE CASCADE로 같이 지워진다."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM keyword_groups WHERE id = ? AND user_id = ?", (group_id, user_id)
        )
        return cursor.rowcount > 0


def add_keyword(user_id: int, group_id: int, keyword_text: str) -> dict | None:
    """
    그룹에 키워드를 하나 추가한다. 그룹이 이 사용자 소유가 맞는지 먼저 확인하고,
    아니면(다른 사람 그룹이거나 없는 그룹이면) None을 반환해 API가 404/403으로
    처리할 수 있게 한다.
    """
    with get_connection() as conn:
        owned = conn.execute(
            "SELECT id FROM keyword_groups WHERE id = ? AND user_id = ?", (group_id, user_id)
        ).fetchone()
        if owned is None:
            return None

        cursor = conn.execute(
            "INSERT INTO keywords (group_id, keyword_text) VALUES (?, ?)",
            (group_id, keyword_text),
        )
        return {"id": cursor.lastrowid, "text": keyword_text}


def delete_keyword(user_id: int, keyword_id: int) -> bool:
    """
    키워드 하나를 삭제한다. keywords 테이블 자체에는 user_id가 없으므로,
    keyword_groups와 조인해서 "이 키워드가 속한 그룹이 이 사용자 소유인지"를
    같이 확인한다.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """
            DELETE FROM keywords
            WHERE id = ?
              AND group_id IN (SELECT id FROM keyword_groups WHERE user_id = ?)
            """,
            (keyword_id, user_id),
        )
        return cursor.rowcount > 0


def update_kakao_tokens(
    user_id: int, access_token: str, refresh_token: str, expires_at: datetime
) -> None:
    """
    카카오 access_token을 갱신한 뒤 DB에 반영한다 (kakao_sender.refresh_user_access_token
    에서 호출). 개인용 스크립트가 kakao_token.json 파일에 쓰는 것의 웹 서비스판.
    """
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE users
            SET kakao_access_token = ?, kakao_refresh_token = ?, kakao_token_expires_at = ?
            WHERE id = ?
            """,
            (access_token, refresh_token, expires_at, user_id),
        )


def get_sent_paper_ids(user_id: int) -> set:
    """이 사용자에게 이미 보낸 논문의 hf_id 집합. collector.collect_papers(seen_ids=...)에 넘긴다."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT hf_id FROM sent_papers WHERE user_id = ?", (user_id,)
        ).fetchall()
        return {row["hf_id"] for row in rows}


def mark_papers_sent(user_id: int, hf_ids: list[str]) -> None:
    """방금 발송한 논문들을 이 사용자의 발송 이력에 기록해서 다음에 중복 발송되지 않게 한다."""
    with get_connection() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO sent_papers (user_id, hf_id) VALUES (?, ?)",
            [(user_id, hf_id) for hf_id in hf_ids],
        )
