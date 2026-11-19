"""
PostgreSQL 기반 사용자 저장소. 카카오 소셜 로그인이 곧 회원가입이라 password 필드는 없고,
카카오 access/refresh token도 users 테이블에 같이 저장한다.

7-1-f에서 SQLite(app.db)에서 PostgreSQL로 옮겼다 - 공용 논문 풀(pool_db.py)과 같은 DB를 쓰고,
8번 배포 때 AWS RDS로 그대로 옮긴다. 함수 이름/인자/반환 형태는 SQLite 시절과 같아서
server.py, kakao_sender.py는 바뀌지 않았다.
"""

import os
from contextlib import contextmanager
from datetime import datetime

import psycopg
from psycopg.rows import dict_row

# docker-compose의 db 서비스 기본값과 맞춘 로컬 개발용 기본값. 웹 컨테이너 안에서는
# docker-compose.yml이 호스트를 db(서비스 이름)로 바꾼 DATABASE_URL을 주입한다.
DEFAULT_DATABASE_URL = "postgresql://paper:paper@localhost:5432/paper"


def database_url() -> str:
    # import 시점이 아니라 연결 시점에 읽는다 - server.py/load_pool.py는 이 모듈을 import한 뒤에
    # load_dotenv()를 호출하므로, 모듈 상단에서 읽으면 .env의 DATABASE_URL이 무시된다.
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kakao_id TEXT UNIQUE NOT NULL,
    nickname TEXT,
    profile_image_url TEXT,
    kakao_access_token TEXT NOT NULL,
    kakao_refresh_token TEXT NOT NULL,
    kakao_token_expires_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS keyword_groups (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('manual', 'llm_chat')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS keyword_groups_user_id_idx ON keyword_groups (user_id);

-- ON DELETE CASCADE는 PostgreSQL에서 기본으로 동작한다 (SQLite 시절의 PRAGMA foreign_keys 불필요).
CREATE TABLE IF NOT EXISTS keywords (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_id BIGINT NOT NULL REFERENCES keyword_groups(id) ON DELETE CASCADE,
    keyword_text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS keywords_group_id_idx ON keywords (group_id);

-- 사용자마다 "이미 보낸 논문"이 달라야 하므로(개인용 스크립트의 전역 seen_papers.json과
-- 달리) 사용자별로 발송 이력을 남긴다. UNIQUE(user_id, hf_id)로 같은 논문을 같은
-- 사용자에게 중복 저장하는 걸 막는다.
CREATE TABLE IF NOT EXISTS sent_papers (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    hf_id TEXT NOT NULL,
    sent_at TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (user_id, hf_id)
);
"""


@contextmanager
def get_connection():
    """
    with 블록 하나 = 트랜잭션 하나. 정상 종료면 commit, 예외면 rollback.
    SQLite 시절처럼 호출마다 새로 연결한다 (요청 수가 적은 지금 규모에서는 충분 -
    배포 후 부하가 생기면 psycopg_pool로 바꾼다).
    """
    conn = psycopg.connect(database_url(), row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """
    테이블이 없으면 만든다. 앞으로 기존 테이블에 컬럼을 추가할 때는 SCHEMA의 CREATE TABLE에
    컬럼을 넣고, 아래에 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...`를 함께 추가한다
    (이미 만들어진 테이블에는 CREATE TABLE IF NOT EXISTS가 새 컬럼을 넣어주지 않기 때문).
    SQLite 시절의 _migrate()(PRAGMA table_info로 컬럼 존재 확인)를 PostgreSQL 문법 한 줄로 대체한 것.
    """
    with get_connection() as conn:
        conn.execute(SCHEMA)


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
    ON CONFLICT ... DO UPDATE (upsert 문법)가 그 "있으면 갱신, 없으면
    생성"을 한 번의 쿼리로 처리해준다.
    """
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (kakao_id, nickname, profile_image_url,
                                kakao_access_token, kakao_refresh_token, kakao_token_expires_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT(kakao_id) DO UPDATE SET
                nickname = excluded.nickname,
                profile_image_url = excluded.profile_image_url,
                kakao_access_token = excluded.kakao_access_token,
                kakao_refresh_token = excluded.kakao_refresh_token,
                kakao_token_expires_at = excluded.kakao_token_expires_at
            """,
            (kakao_id, nickname, profile_image_url, access_token, refresh_token, expires_at),
        )
        row = conn.execute("SELECT id FROM users WHERE kakao_id = %s", (kakao_id,)).fetchone()
        return row["id"]


def get_user(user_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()
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
        # PostgreSQL에는 SQLite의 lastrowid가 없어서 RETURNING으로 새 id를 받는다.
        group_id = conn.execute(
            "INSERT INTO keyword_groups (user_id, title, source) VALUES (%s, %s, %s) RETURNING id",
            (user_id, title, source),
        ).fetchone()["id"]

        saved_keywords = []
        for kw in keywords:
            kw_id = conn.execute(
                "INSERT INTO keywords (group_id, keyword_text) VALUES (%s, %s) RETURNING id",
                (group_id, kw),
            ).fetchone()["id"]
            saved_keywords.append({"id": kw_id, "text": kw})

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
            "WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()

        result = []
        for group in groups:
            keyword_rows = conn.execute(
                "SELECT id, keyword_text FROM keywords WHERE group_id = %s", (group["id"],)
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
            "UPDATE keyword_groups SET is_active = %s WHERE id = %s AND user_id = %s",
            (is_active, group_id, user_id),
        )
        return cursor.rowcount > 0


def update_keyword_group_title(user_id: int, group_id: int, title: str) -> bool:
    """
    그룹 제목을 수정한다. WHERE 절에 user_id도 같이 넣어서, 남의 그룹 id를 넣어도
    수정되지 않도록 막는다 (소유권 확인). 실제로 수정된 행이 있었으면 True.
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "UPDATE keyword_groups SET title = %s WHERE id = %s AND user_id = %s",
            (title, group_id, user_id),
        )
        return cursor.rowcount > 0


def delete_keyword_group(user_id: int, group_id: int) -> bool:
    """그룹을 통째로 삭제한다. 소속 keywords는 ON DELETE CASCADE로 같이 지워진다."""
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM keyword_groups WHERE id = %s AND user_id = %s", (group_id, user_id)
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
            "SELECT id FROM keyword_groups WHERE id = %s AND user_id = %s", (group_id, user_id)
        ).fetchone()
        if owned is None:
            return None

        kw_id = conn.execute(
            "INSERT INTO keywords (group_id, keyword_text) VALUES (%s, %s) RETURNING id",
            (group_id, keyword_text),
        ).fetchone()["id"]
        return {"id": kw_id, "text": keyword_text}


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
            WHERE id = %s
              AND group_id IN (SELECT id FROM keyword_groups WHERE user_id = %s)
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
            SET kakao_access_token = %s, kakao_refresh_token = %s, kakao_token_expires_at = %s
            WHERE id = %s
            """,
            (access_token, refresh_token, expires_at, user_id),
        )


def get_sent_paper_ids(user_id: int) -> set:
    """이 사용자에게 이미 보낸 논문의 hf_id 집합. collector.collect_papers(seen_ids=...)에 넘긴다."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT hf_id FROM sent_papers WHERE user_id = %s", (user_id,)
        ).fetchall()
        return {row["hf_id"] for row in rows}


def mark_papers_sent(user_id: int, hf_ids: list[str]) -> None:
    """방금 발송한 논문들을 이 사용자의 발송 이력에 기록해서 다음에 중복 발송되지 않게 한다."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO sent_papers (user_id, hf_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            [(user_id, hf_id) for hf_id in hf_ids],
        )
