"""
ReadingStore - "AI와 함께 읽기" 에이전트가 저장소에 요구하는 기능 목록 (DB 파트와의 계약).

에이전트 코드는 이 프로토콜의 메서드만 호출하고, 어떤 DB/벡터 DB/임베딩 모델/BM25
구현을 쓰는지는 전혀 모른다. 그래서 DB 파트가 완성되면:

    1. 이 프로토콜을 만족하는 클래스(예: reading/sql_store.py의 SqlReadingStore)를 만들고
    2. 아래 get_store()의 분기에 한 줄 추가한 뒤
    3. READING_STORE 환경변수로 선택

하면 에이전트 모듈은 한 줄도 고치지 않고 통합된다. 테스트용 구현은 fake_store.py 참고.

설계 판단:
- 검색 메서드는 "질의 문자열"을 받는다 (임베딩 벡터가 아님). 임베딩 모델과 벡터 DB는
  한 쌍으로 묶여 있는 DB 쪽 결정이라, 쿼리 임베딩도 저장소 안에서 하는 게 경계가 깔끔하다.
- 벡터 검색과 BM25를 별개 메서드로 둔다. 둘을 합치는 RRF와 가중치(섹션/중요도)는
  CLAUDE.md에 확정된 에이전트 쪽 로직이라 retrieval.py가 맡는다.
- candidate_ids=None은 "필터 없이 공용 풀 전체"를 뜻한다 (필터 완화 시 사용).
"""

import os
from typing import Protocol, runtime_checkable

from reading.schemas import AbstractHit, Briefing, ChunkHit, PaperMeta, PoolCoverage, Reference


@runtime_checkable
class ReadingStore(Protocol):
    # ---- 관계형 DB ----
    def get_papers(self, paper_ids: list[str]) -> dict[str, PaperMeta]:
        """paper_id -> 메타데이터. 없는 id는 결과에서 빠진다."""
        ...

    def get_briefing(self, paper_id: str) -> Briefing | None:
        """발송 결정 시 만들어 둔 브리핑. 아직 생성 전이면 None."""
        ...

    def get_references(self, paper_id: str) -> list[Reference]:
        """본 논문의 레퍼런스 목록 (중요도 점수 포함). 수집 전이면 빈 리스트."""
        ...

    def normalize_keywords(self, keywords: list[str]) -> list[str]:
        """
        별칭 사전으로 키워드를 정규화 키워드 id 목록으로 바꾼다. 사전에 없는 키워드는
        조용히 버린다 (CLAUDE.md "키워드 정규화" - 사전에 없는 경우는 지금 처리하지 않음).
        """
        ...

    def filter_pool_by_keywords(self, keyword_ids: list[str]) -> list[str]:
        """정규화 키워드 id 중 하나라도 붙은 공용 풀 논문의 paper_id 목록 (메타데이터 필터링)."""
        ...

    def pool_coverage(self) -> PoolCoverage:
        """공용 풀이 갱신돼 있는 기간 - 답변에 검색 범위를 밝힐 때 쓴다."""
        ...

    # ---- 벡터 DB / BM25 인덱스 ----
    def vector_search_abstracts(
        self, query: str, candidate_ids: list[str] | None, k: int
    ) -> list[AbstractHit]:
        """공용 풀 초록 임베딩 검색. 점수 내림차순."""
        ...

    def bm25_search_abstracts(
        self, query: str, candidate_ids: list[str] | None, k: int
    ) -> list[AbstractHit]:
        """공용 풀 초록 BM25 검색. 점수 내림차순."""
        ...

    def vector_search_chunks(self, query: str, paper_ids: list[str], k: int) -> list[ChunkHit]:
        """지정한 논문들의 전문 청크 안에서 임베딩 검색. 점수 내림차순."""
        ...

    def bm25_search_chunks(self, query: str, paper_ids: list[str], k: int) -> list[ChunkHit]:
        """지정한 논문들의 전문 청크 안에서 BM25 검색 (표/수치 질문 대비). 점수 내림차순."""
        ...


def get_store() -> ReadingStore:
    """
    READING_STORE 환경변수로 저장소 구현을 고른다. DB 파트 통합 전까지는 fake가 기본값.
    DB 파트 통합 시 여기에 분기 하나만 추가하면 된다, 예:
        if kind == "sql":
            from reading.sql_store import SqlReadingStore
            return SqlReadingStore()
    """
    kind = os.environ.get("READING_STORE", "fake")
    if kind == "fake":
        from reading.fake_store import FakeReadingStore

        return FakeReadingStore.from_fixture()
    raise ValueError(f"알 수 없는 READING_STORE 값: {kind!r}")
