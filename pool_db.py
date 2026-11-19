"""
공용 논문 풀(로드맵 7번) 스키마.

사용자 테이블(db.py)과 같은 PostgreSQL을 쓰므로 연결은 db.get_connection()을 그대로 쓴다.

에이전트 코드는 이 모듈을 직접 쓰지 않고 paper_pool.py의 접근 함수만 호출한다
(docs/paper_pool_interface.md 참고) - 이 파일은 DB 담당 쪽 내부 구현이다.
"""

import re

from db import get_connection

# 테이블 이름에 oa_ 접두사를 붙인 이유: 사용자 키워드 테이블(db.py) 이름이 이미 keywords라
# 같은 DB 안에서 이름이 충돌한다.
SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

-- 공용 풀: 제목+초록만 (전문은 7-3에서 논문별 청크로 따로 저장).
-- paper_id는 버전 접미사 없는 arXiv ID ("2005.11401", "cs/9901001") - HF hf_id와 같은 체계.
CREATE TABLE IF NOT EXISTS pool_papers (
    paper_id       TEXT PRIMARY KEY,
    openalex_id    TEXT UNIQUE,
    title          TEXT NOT NULL,
    abstract       TEXT NOT NULL,
    categories     TEXT[] NOT NULL,
    published_date DATE,
    source         TEXT NOT NULL DEFAULT 'kaggle'
                   CHECK (source IN ('kaggle', 'arxiv_api', 'semantic_scholar', 'reference')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- 키워드 검색(search_text)용. 제목에 가중치 A, 초록에 B.
    -- 엄밀한 BM25는 아님 - BM25 확장 사용 여부는 7-4에서 결정 (CLAUDE.md 미결 사항).
    search_tsv     tsvector GENERATED ALWAYS AS (
                       setweight(to_tsvector('english', title), 'A') ||
                       setweight(to_tsvector('english', abstract), 'B')
                   ) STORED
);
CREATE INDEX IF NOT EXISTS pool_papers_search_tsv_idx ON pool_papers USING GIN (search_tsv);
CREATE INDEX IF NOT EXISTS pool_papers_published_date_idx ON pool_papers (published_date);

-- OpenAlex 키워드 개체 (풀에 한 번이라도 등장한 것만).
CREATE TABLE IF NOT EXISTS oa_keywords (
    keyword_id   TEXT PRIMARY KEY,          -- slug, 예: "retrieval-augmented-generation"
    display_name TEXT NOT NULL,
    works_count  INTEGER
);

-- 별칭 사전: 정규화된 표현 -> keyword_id. OpenAlex 별칭은 모호할 수 있어서
-- (예: transformer의 별칭에 "electrical transformer models") 한 표현이 여러 keyword_id에
-- 걸릴 수 있게 (alias_norm, keyword_id)를 복합 키로 둔다.
CREATE TABLE IF NOT EXISTS keyword_aliases (
    alias_norm TEXT NOT NULL,
    keyword_id TEXT NOT NULL REFERENCES oa_keywords(keyword_id) ON DELETE CASCADE,
    is_primary BOOLEAN NOT NULL,            -- display_name 자체면 true, 별칭이면 false
    PRIMARY KEY (alias_norm, keyword_id)
);

-- 논문-키워드 연결 (OpenAlex가 매긴 score 포함). find_candidates()가 keyword_id로 조회한다.
CREATE TABLE IF NOT EXISTS paper_keywords (
    paper_id   TEXT NOT NULL REFERENCES pool_papers(paper_id) ON DELETE CASCADE,
    keyword_id TEXT NOT NULL REFERENCES oa_keywords(keyword_id) ON DELETE CASCADE,
    score      REAL NOT NULL,
    PRIMARY KEY (paper_id, keyword_id)
);
CREATE INDEX IF NOT EXISTS paper_keywords_keyword_id_idx ON paper_keywords (keyword_id);

-- 풀 갱신 시각 등 단일 값 메타데이터 (pool_coverage()의 updated_at).
CREATE TABLE IF NOT EXISTS pool_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def init_pool_db() -> None:
    with get_connection() as conn:
        conn.execute(SCHEMA)


_SEPARATORS = re.compile(r"[\s\-_]+")


def normalize_keyword_text(text: str) -> str:
    """
    별칭 사전의 비교 키. 적재(alias_norm 생성)와 조회(normalize_keywords) 양쪽이 반드시
    이 함수 하나를 써야 같은 표현이 같은 키로 맞는다.
    소문자 + 하이픈/언더스코어/연속 공백 -> 공백 1개 + 앞뒤 공백 제거.
    예: "Retrieval-Augmented  Generation" -> "retrieval augmented generation"
    """
    return _SEPARATORS.sub(" ", text.lower()).strip()
